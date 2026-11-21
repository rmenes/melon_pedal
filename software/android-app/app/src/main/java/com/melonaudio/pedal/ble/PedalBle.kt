package com.melonaudio.pedal.ble

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.BluetoothStatusCodes
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Build
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import java.io.ByteArrayOutputStream
import java.util.UUID

/**
 * BLE link to melon-ble on the pedal: a "UART over BLE".
 * Phone writes JSON lines to RX, the pedal notifies JSON lines on TX.
 * Lines can be longer than one BLE packet; '\n' marks the end of each line.
 *
 * Permissions (BLUETOOTH_SCAN / BLUETOOTH_CONNECT, or location on Android 11 and
 * older) are requested by the UI before any of this is called.
 */
@SuppressLint("MissingPermission")
class PedalBle(private val context: Context, private val scope: CoroutineScope) {

    companion object {
        val SERVICE: UUID = UUID.fromString("6d656c6f-6e70-6564-616c-000000000000")
        val RX: UUID = UUID.fromString("6d656c6f-6e70-6564-616c-000000000001")
        val TX: UUID = UUID.fromString("6d656c6f-6e70-6564-616c-000000000002")
        val CCCD: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
        private const val WANTED_MTU = 517
        private const val MAX_LINE = 256 * 1024
    }

    sealed interface Status {
        data object Disconnected : Status
        data object Connecting : Status
        data object Ready : Status
        data class Lost(val reason: String) : Status
    }

    data class Found(val address: String, val name: String, val rssi: Int)

    private val manager = context.getSystemService(BluetoothManager::class.java)
    val adapter: BluetoothAdapter? get() = manager?.adapter
    val isEnabled: Boolean get() = adapter?.isEnabled == true

    private val _status = MutableStateFlow<Status>(Status.Disconnected)
    val status: StateFlow<Status> = _status.asStateFlow()

    private val _lines = MutableSharedFlow<String>(extraBufferCapacity = 1024)
    val lines: SharedFlow<String> = _lines.asSharedFlow()

    @Volatile private var gatt: BluetoothGatt? = null
    @Volatile private var rx: BluetoothGattCharacteristic? = null
    @Volatile private var mtu = 23
    @Volatile private var userClosed = false
    private val inBuf = ByteArrayOutputStream()
    private val outQueue = Channel<ByteArray>(Channel.UNLIMITED)
    @Volatile private var writeDone: CompletableDeferred<Boolean>? = null
    private var writerJob: Job? = null

    // ---------------------------------------------------------------- scanning
    fun scan(): Flow<Found> = callbackFlow {
        val scanner = adapter?.bluetoothLeScanner
        if (scanner == null) {
            close(IllegalStateException("Bluetooth is off"))
            return@callbackFlow
        }
        val cb = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, r: ScanResult) {
                val uuids = r.scanRecord?.serviceUuids.orEmpty()
                val name = r.scanRecord?.deviceName ?: r.device.name
                if (uuids.any { it.uuid == SERVICE } || name?.startsWith("Melon") == true) {
                    trySend(Found(r.device.address, name ?: "Melon Pedal", r.rssi))
                }
            }

            override fun onScanFailed(errorCode: Int) {
                close(IllegalStateException("Bluetooth scan failed (code $errorCode)"))
            }
        }
        val settings = ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build()
        scanner.startScan(null, settings, cb)
        awaitClose { runCatching { scanner.stopScan(cb) } }
    }

    // -------------------------------------------------------------- connection
    fun connect(address: String) {
        close()
        userClosed = false
        val device = try { adapter?.getRemoteDevice(address) } catch (e: IllegalArgumentException) { null }
        if (device == null) {
            _status.value = Status.Lost("Unknown device")
            return
        }
        _status.value = Status.Connecting
        synchronized(inBuf) { inBuf.reset() }
        mtu = 23
        gatt = device.connectGatt(context, false, callback, BluetoothDevice.TRANSPORT_LE)
    }

    fun close() {
        userClosed = true
        writerJob?.cancel()
        writerJob = null
        writeDone?.complete(false)
        gatt?.let {
            runCatching { it.disconnect() }
            runCatching { it.close() }
        }
        gatt = null
        rx = null
        while (outQueue.tryReceive().isSuccess) { /* drop unsent lines */ }
        _status.value = Status.Disconnected
    }

    /** Queue one JSON line for the pedal. */
    fun send(line: String) {
        if (_status.value == Status.Ready) outQueue.trySend((line + "\n").toByteArray(Charsets.UTF_8))
    }

    private fun fail(g: BluetoothGatt, reason: String) {
        runCatching { g.disconnect() }
        runCatching { g.close() }
        if (g == gatt) {
            gatt = null
            rx = null
            writerJob?.cancel()
            writeDone?.complete(false)
            if (!userClosed) _status.value = Status.Lost(reason)
        }
    }

    private val callback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            if (status == BluetoothGatt.GATT_SUCCESS && newState == BluetoothProfile.STATE_CONNECTED) {
                if (!g.requestMtu(WANTED_MTU)) g.discoverServices()
            } else {
                val reason = when (status) {
                    8 -> "Pedal out of range"
                    19 -> "Pedal closed the connection"
                    133 -> "Could not connect (is the pedal on?)"
                    else -> if (newState == BluetoothProfile.STATE_DISCONNECTED) "Disconnected" else "Bluetooth error $status"
                }
                fail(g, reason)
            }
        }

        override fun onMtuChanged(g: BluetoothGatt, newMtu: Int, status: Int) {
            mtu = if (status == BluetoothGatt.GATT_SUCCESS) newMtu else 23
            g.discoverServices()
        }

        @Suppress("DEPRECATION")
        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
            val service = g.getService(SERVICE)
            val rxChar = service?.getCharacteristic(RX)
            val txChar = service?.getCharacteristic(TX)
            val cccd = txChar?.getDescriptor(CCCD)
            if (status != BluetoothGatt.GATT_SUCCESS || rxChar == null || txChar == null || cccd == null) {
                fail(g, "This device is not a Melon Pedal (or melon-ble is not running)")
                return
            }
            rx = rxChar
            g.setCharacteristicNotification(txChar, true)
            val enable = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
            val started = if (Build.VERSION.SDK_INT >= 33) {
                g.writeDescriptor(cccd, enable) == BluetoothStatusCodes.SUCCESS
            } else {
                cccd.value = enable
                g.writeDescriptor(cccd)
            }
            if (!started) fail(g, "Could not subscribe to the pedal")
        }

        override fun onDescriptorWrite(g: BluetoothGatt, d: BluetoothGattDescriptor, status: Int) {
            if (d.uuid != CCCD) return
            if (status != BluetoothGatt.GATT_SUCCESS) {
                fail(g, "Could not subscribe to the pedal ($status)")
                return
            }
            startWriter()
            g.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)
            _status.value = Status.Ready
        }

        override fun onCharacteristicChanged(g: BluetoothGatt, c: BluetoothGattCharacteristic, value: ByteArray) {
            if (c.uuid == TX) onData(value)
        }

        @Deprecated("Android 12 and older")
        @Suppress("DEPRECATION")
        override fun onCharacteristicChanged(g: BluetoothGatt, c: BluetoothGattCharacteristic) {
            // Android 13+ calls the ByteArray version above as well; only handle it here on older versions.
            if (Build.VERSION.SDK_INT < 33 && c.uuid == TX) onData(c.value ?: return)
        }

        override fun onCharacteristicWrite(g: BluetoothGatt, c: BluetoothGattCharacteristic, status: Int) {
            writeDone?.complete(status == BluetoothGatt.GATT_SUCCESS)
        }
    }

    private fun onData(bytes: ByteArray) {
        synchronized(inBuf) {
            for (b in bytes) {
                if (b == '\n'.code.toByte()) {
                    val line = inBuf.toString(Charsets.UTF_8.name())
                    inBuf.reset()
                    if (line.isNotBlank()) _lines.tryEmit(line)
                } else {
                    inBuf.write(b.toInt())
                    if (inBuf.size() > MAX_LINE) inBuf.reset()
                }
            }
        }
    }

    // ----------------------------------------------------------------- writing
    // Android allows one GATT operation at a time, so lines are written chunk by chunk,
    // each chunk waiting for onCharacteristicWrite before the next.
    private fun startWriter() {
        writerJob?.cancel()
        writerJob = scope.launch(Dispatchers.IO) {
            for (msg in outQueue) {
                val size = (mtu - 3).coerceIn(20, 512)
                var off = 0
                while (off < msg.size) {
                    val end = minOf(off + size, msg.size)
                    if (!writeChunk(msg.copyOfRange(off, end))) break
                    off = end
                }
            }
        }
    }

    @Suppress("DEPRECATION")
    private suspend fun writeChunk(bytes: ByteArray): Boolean {
        repeat(5) {
            val g = gatt ?: return false
            val c = rx ?: return false
            val done = CompletableDeferred<Boolean>()
            writeDone = done
            val started = if (Build.VERSION.SDK_INT >= 33) {
                g.writeCharacteristic(c, bytes, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) ==
                    BluetoothStatusCodes.SUCCESS
            } else {
                c.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
                c.value = bytes
                g.writeCharacteristic(c)
            }
            if (started) return withTimeoutOrNull(3000) { done.await() } ?: false
            delay(30)   // stack busy (e.g. still subscribing): try again
        }
        return false
    }
}
