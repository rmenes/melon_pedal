package com.melonaudio.pedal

import android.app.Application
import android.content.Context
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.melonaudio.pedal.ble.PedalBle
import com.melonaudio.pedal.data.PedalState
import com.melonaudio.pedal.data.Protocol
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

class PedalViewModel(app: Application) : AndroidViewModel(app) {

    private val ble = PedalBle(app, viewModelScope)
    private val prefs = app.getSharedPreferences("melon", Context.MODE_PRIVATE)

    val status: StateFlow<PedalBle.Status> = ble.status

    private val _state = MutableStateFlow(PedalState())
    val state: StateFlow<PedalState> = _state.asStateFlow()

    private val _found = MutableStateFlow<List<PedalBle.Found>>(emptyList())
    val found: StateFlow<List<PedalBle.Found>> = _found.asStateFlow()

    private val _scanning = MutableStateFlow(false)
    val scanning: StateFlow<Boolean> = _scanning.asStateFlow()

    private val _scanError = MutableStateFlow<String?>(null)
    val scanError: StateFlow<String?> = _scanError.asStateFlow()

    private var scanJob: Job? = null

    /** Parameter index -> time the user last moved it on the phone. */
    private val localEdits = HashMap<Int, Long>()
    /** Latest slider values not sent yet (sent ~30 times per second, newest value only). */
    private val pending = LinkedHashMap<Int, Pair<Int, Float>>()   // index -> (plugin gen, value)

    val lastAddress: String? get() = prefs.getString("last_pedal", null)
    val bluetoothOn: Boolean get() = ble.isEnabled

    init {
        viewModelScope.launch {
            ble.lines.collect { line ->
                _state.update { Protocol.apply(it, line, ::isLocal) }
            }
        }
        viewModelScope.launch {
            ble.status.collect { if (it == PedalBle.Status.Ready) ble.send(Protocol.hello()) }
        }
        viewModelScope.launch {
            while (true) {
                delay(33)
                flush()
            }
        }
    }

    private fun isLocal(i: Int): Boolean {
        val t = synchronized(localEdits) { localEdits[i] } ?: return false
        return System.currentTimeMillis() - t < 400
    }

    private fun flush() {
        val batch = synchronized(pending) { LinkedHashMap(pending).also { pending.clear() } }
        for ((i, gv) in batch) ble.send(Protocol.set(gv.first, i, gv.second))
    }

    // ------------------------------------------------------------------ scan
    fun startScan() {
        scanJob?.cancel()
        _found.value = emptyList()
        _scanError.value = null
        scanJob = viewModelScope.launch {
            _scanning.value = true
            try {
                withTimeoutOrNull(15_000) {
                    ble.scan().collect { f ->
                        _found.update { list -> (list.filter { it.address != f.address } + f).sortedByDescending { it.rssi } }
                    }
                }
            } catch (e: Exception) {
                _scanError.value = e.message
            } finally {
                _scanning.value = false
            }
        }
    }

    fun stopScan() {
        scanJob?.cancel()
        _scanning.value = false
    }

    fun connect(address: String) {
        stopScan()
        prefs.edit().putString("last_pedal", address).apply()
        _state.value = PedalState()
        ble.connect(address)
    }

    fun disconnect() {
        ble.close()
        _state.value = PedalState()
    }

    // --------------------------------------------------------------- actions
    fun setValue(i: Int, v: Float) {
        val s = _state.value
        val gen = s.plugin?.gen ?: return
        if (i !in s.values.indices) return
        synchronized(localEdits) { localEdits[i] = System.currentTimeMillis() }
        synchronized(pending) { pending[i] = gen to v }
        _state.update { it.copy(values = it.values.toMutableList().also { vals -> if (i in vals.indices) vals[i] = v }) }
    }

    fun resetValue(i: Int) {
        val c = _state.value.plugin?.controls?.getOrNull(i) ?: return
        setValue(i, c.default)
    }

    fun toggleBypass() {
        val on = !_state.value.bypass
        _state.update { it.copy(bypass = on) }
        ble.send(Protocol.bypass(on))
    }

    fun putPageOnKnobs(page: Int) = ble.send(Protocol.page(page))
    fun loadPlugin(i: Int) = ble.send(Protocol.loadPlugin(i))
    fun loadPreset(slot: Int) = ble.send(Protocol.loadPreset(slot))
    fun savePreset(slot: Int, name: String) = ble.send(Protocol.savePreset(slot, Protocol.cleanName(name)))
    fun clearError() = _state.update { it.copy(error = null) }

    // ------------------------------------------------------ NAM / IR library
    /** Ask the pedal for one folder of the library behind control [i] ("" = top level). */
    fun openFolder(i: Int, folder: String) {
        val gen = _state.value.plugin?.gen ?: return
        _state.update { it.copy(listing = null) }          // show "loading" until the answer arrives
        ble.send(Protocol.libList(gen, i, folder))
    }

    /** Load [path] (inside the library; null = no file) into control [i]. */
    fun chooseFile(i: Int, path: String?) {
        val gen = _state.value.plugin?.gen ?: return
        _state.update { st ->
            st.copy(files = st.files.toMutableList().also { if (i in it.indices) it[i] = path }, listing = null)
        }
        ble.send(Protocol.setFile(gen, i, path))
    }

    fun closeLibrary() = _state.update { it.copy(listing = null) }

    // ------------------------------------------------------------------ Wi-Fi
    fun wifiRefresh() = ble.send(Protocol.wifiStatus())
    fun wifiScan() {
        _state.update { it.copy(wifi = it.wifi.copy(busy = "Scanning…")) }
        ble.send(Protocol.wifiScan())
    }
    fun wifiConnect(ssid: String, password: String?, hidden: Boolean = false) {
        _state.update { it.copy(wifi = it.wifi.copy(busy = "Connecting to $ssid…", result = null)) }
        ble.send(Protocol.wifiConnect(ssid, password?.takeIf { it.isNotEmpty() }, hidden))
    }
    fun wifiForget(ssid: String) = ble.send(Protocol.wifiForget(ssid))
    fun clearWifiResult() = _state.update { it.copy(wifi = it.wifi.copy(result = null)) }

    override fun onCleared() {
        ble.close()
    }
}
