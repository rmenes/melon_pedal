package com.melonaudio.pedal

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.melonaudio.pedal.ble.PedalBle
import com.melonaudio.pedal.ui.Melon
import com.melonaudio.pedal.ui.MelonTheme
import com.melonaudio.pedal.ui.PedalScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MelonTheme {
                Surface(color = Melon.ground, modifier = Modifier.fillMaxSize()) {
                    App()
                }
            }
        }
    }
}

private val PERMISSIONS: Array<String> =
    if (Build.VERSION.SDK_INT >= 31) arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
    else arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)

@Composable
fun App(vm: PedalViewModel = viewModel()) {
    val context = LocalContext.current
    val status by vm.status.collectAsStateWithLifecycle()
    var granted by remember {
        mutableStateOf(PERMISSIONS.all { ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED })
    }
    val askPermissions = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { res ->
        granted = res.values.all { it }
    }

    Column(Modifier.fillMaxSize().safeDrawingPadding()) {
        when {
            !granted -> PermissionScreen { askPermissions.launch(PERMISSIONS) }
            status == PedalBle.Status.Ready -> PedalScreen(vm)
            else -> ConnectScreen(vm, status)
        }
    }
}

@Composable
private fun PermissionScreen(onAsk: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Title()
        Spacer(Modifier.height(24.dp))
        Text(
            "The app needs Bluetooth permission to find and talk to your pedal.",
            color = Melon.sage, textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(24.dp))
        Button(onClick = onAsk) { Text("Allow Bluetooth") }
    }
}

@Composable
private fun Title() {
    Text("Melon Pedal", color = Melon.cream, fontSize = 32.sp, fontWeight = FontWeight.SemiBold)
    Text("remote", color = Melon.lime, fontSize = 14.sp, letterSpacing = 4.sp)
}

@Composable
private fun ConnectScreen(vm: PedalViewModel, status: PedalBle.Status) {
    val found by vm.found.collectAsStateWithLifecycle()
    val scanning by vm.scanning.collectAsStateWithLifecycle()
    val scanError by vm.scanError.collectAsStateWithLifecycle()
    // re-check Bluetooth after the "turn on" dialog closes
    var btTick by remember { mutableIntStateOf(0) }
    val enableBt = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { btTick++ }
    val btOn = remember(btTick) { vm.bluetoothOn }

    LaunchedEffect(btOn) {
        if (btOn && status == PedalBle.Status.Disconnected && found.isEmpty()) vm.startScan()
    }

    Column(Modifier.fillMaxSize().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Spacer(Modifier.height(32.dp))
        Title()
        Spacer(Modifier.height(32.dp))

        when (status) {
            PedalBle.Status.Connecting -> {
                CircularProgressIndicator(color = Melon.lime)
                Spacer(Modifier.height(12.dp))
                Text("Connecting…", color = Melon.sage)
                TextButton(onClick = { vm.disconnect() }) { Text("Cancel") }
                return@Column
            }
            is PedalBle.Status.Lost -> {
                Text(status.reason, color = Melon.amber, textAlign = TextAlign.Center)
                Spacer(Modifier.height(8.dp))
                vm.lastAddress?.let { addr -> Button(onClick = { vm.connect(addr) }) { Text("Reconnect") } }
                Spacer(Modifier.height(16.dp))
            }
            else -> {}
        }

        if (!btOn) {
            Text("Bluetooth is off.", color = Melon.amber)
            Spacer(Modifier.height(8.dp))
            Button(onClick = { enableBt.launch(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE)) }) { Text("Turn on Bluetooth") }
            return@Column
        }

        Row(verticalAlignment = Alignment.CenterVertically) {
            if (scanning) {
                CircularProgressIndicator(Modifier.size(18.dp), color = Melon.lime, strokeWidth = 2.dp)
                Spacer(Modifier.padding(6.dp))
                Text("Looking for pedals…", color = Melon.sage)
            } else {
                OutlinedButton(onClick = { vm.startScan() }) { Text("Search again") }
            }
        }
        scanError?.let { Text(it, color = Melon.amber, modifier = Modifier.padding(top = 8.dp)) }
        Spacer(Modifier.height(16.dp))

        if (found.isEmpty() && !scanning) {
            Text(
                "No pedal found. Is it switched on, and is the melon-ble service running on it?",
                color = Melon.dim, textAlign = TextAlign.Center,
            )
        }
        LazyColumn(Modifier.fillMaxWidth()) {
            items(found, key = { it.address }) { f ->
                Card(
                    colors = CardDefaults.cardColors(containerColor = Melon.surface),
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp).clickable { vm.connect(f.address) },
                ) {
                    Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(f.name, color = Melon.cream, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                            Text(
                                f.address + if (f.address == vm.lastAddress) " · last used" else "",
                                color = Melon.sage, fontSize = 12.sp,
                            )
                        }
                        Text(signal(f.rssi), color = Melon.lime, fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

private fun signal(rssi: Int) = when {
    rssi > -60 -> "●●●"
    rssi > -75 -> "●●○"
    else -> "●○○"
}
