package com.melonaudio.pedal.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.melonaudio.pedal.PedalViewModel
import com.melonaudio.pedal.data.WifiState
import kotlinx.coroutines.delay

/** What the user tapped: a network to join (password asked if needed) or a hidden one to add. */
private data class JoinTarget(val ssid: String, val secure: Boolean, val known: Boolean, val hidden: Boolean)

/**
 * Wi-Fi of the pedal, set up over Bluetooth: useful in a new place where the pedal
 * doesn't know the network yet. The phone stays connected over Bluetooth while the
 * pedal changes networks.
 */
@Composable
fun WifiScreen(w: WifiState, vm: PedalViewModel, onClose: () -> Unit) {
    var join by remember { mutableStateOf<JoinTarget?>(null) }
    var forget by remember { mutableStateOf<String?>(null) }
    val busy = w.busy != null

    BackHandler(onBack = onClose)
    LaunchedEffect(Unit) {
        vm.wifiRefresh()
        vm.wifiScan()
    }
    w.result?.let { r ->
        LaunchedEffect(r) {
            delay(if (r.ok) 6000 else 10000)
            vm.clearWifiResult()
        }
    }

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onClose) { Text("‹ Back", color = Melon.sage) }
            Text("Pedal Wi-Fi", color = Melon.cream, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
        }

        StatusCard(w)

        if (busy) {
            Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(Modifier.size(16.dp), color = Melon.lime, strokeWidth = 2.dp)
                Spacer(Modifier.width(8.dp))
                Text(w.busy ?: "", color = Melon.sage, fontSize = 14.sp)
            }
        }
        w.result?.let { r ->
            Text(
                r.msg, color = Melon.ground, fontSize = 14.sp,
                modifier = Modifier.fillMaxWidth().padding(top = 10.dp)
                    .background(if (r.ok) Melon.lime else Melon.amber, RoundedCornerShape(6.dp))
                    .clickable { vm.clearWifiResult() }
                    .padding(10.dp),
            )
        }

        Row(Modifier.fillMaxWidth().padding(top = 14.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("NETWORKS NEARBY", color = Melon.sage, fontSize = 12.sp, letterSpacing = 2.sp, modifier = Modifier.weight(1f))
            OutlinedButton(onClick = { vm.wifiScan() }, enabled = !busy) { Text("Scan") }
        }

        LazyColumn(Modifier.weight(1f)) {
            val nets = w.networks
            if (nets == null) {
                item { Text("Scanning for networks…", color = Melon.dim, modifier = Modifier.padding(8.dp)) }
            } else if (nets.isEmpty()) {
                item { Text("No networks found. Tap Scan to try again.", color = Melon.dim, modifier = Modifier.padding(8.dp)) }
            }
            items(nets.orEmpty(), key = { "n-" + it.ssid }) { n ->
                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(vertical = 3.dp)
                        .background(if (n.active) Melon.rind else Melon.surface, RoundedCornerShape(6.dp))
                        .clickable(enabled = !busy && !n.active) { join = JoinTarget(n.ssid, n.secure, n.known, false) }
                        .padding(horizontal = 12.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(n.ssid, color = Melon.cream, fontSize = 17.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(
                            listOfNotNull(
                                if (n.active) "connected" else null,
                                if (n.known && !n.active) "saved" else null,
                                if (n.secure) "🔒 secured" else "open",
                            ).joinToString(" · "),
                            color = if (n.active) Melon.lime else Melon.sage, fontSize = 12.sp,
                        )
                    }
                    Text(bars(n.signal), color = Melon.lime, fontSize = 13.sp)
                }
            }

            if (w.saved.isNotEmpty()) {
                item {
                    Text(
                        "SAVED ON THE PEDAL", color = Melon.sage, fontSize = 12.sp, letterSpacing = 2.sp,
                        modifier = Modifier.padding(top = 16.dp, bottom = 4.dp),
                    )
                }
                items(w.saved, key = { "s-$it" }) { ssid ->
                    Row(
                        Modifier.fillMaxWidth().padding(vertical = 2.dp)
                            .background(Melon.surface, RoundedCornerShape(6.dp)).padding(start = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(ssid, color = Melon.cream, fontSize = 15.sp, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        TextButton(onClick = { forget = ssid }, enabled = !busy) { Text("Forget", color = Melon.amber) }
                    }
                }
            }
            item {
                TextButton(
                    onClick = { join = JoinTarget("", secure = true, known = false, hidden = true) },
                    enabled = !busy, modifier = Modifier.padding(top = 8.dp),
                ) { Text("+ Add hidden network…") }
            }
            item {
                Text(
                    "The pedal keeps every saved network and joins whichever is in range. " +
                        "Your phone stays connected over Bluetooth while the pedal changes Wi-Fi.",
                    color = Melon.dim, fontSize = 12.sp, modifier = Modifier.padding(vertical = 12.dp),
                )
            }
        }
    }

    join?.let { t ->
        JoinDialog(t, onDismiss = { join = null }) { ssid, password ->
            vm.wifiConnect(ssid, password, t.hidden)
            join = null
        }
    }
    forget?.let { ssid ->
        val active = w.status?.ssid == ssid
        AlertDialog(
            onDismissRequest = { forget = null },
            containerColor = Melon.surface,
            title = { Text("Forget $ssid?", color = Melon.cream) },
            text = {
                Text(
                    "The pedal won't join this network by itself anymore." +
                        if (active) " It is connected to it now and will disconnect." else "",
                    color = Melon.sage,
                )
            },
            confirmButton = {
                Button(onClick = { vm.wifiForget(ssid); forget = null }) { Text("Forget") }
            },
            dismissButton = { TextButton(onClick = { forget = null }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun StatusCard(w: WifiState) {
    val st = w.status
    Column(Modifier.fillMaxWidth().background(Melon.surface, RoundedCornerShape(8.dp)).padding(14.dp)) {
        when {
            st == null -> Text("Asking the pedal…", color = Melon.sage)
            st.device == null -> Text("This pedal has no Wi-Fi adapter.", color = Melon.amber)
            st.connected -> {
                Text("CONNECTED", color = Melon.lime, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 2.sp)
                Text(st.ssid ?: "(network)", color = Melon.cream, fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
                Text(
                    listOfNotNull(st.hostname?.let { "$it.local" }, st.signal?.let { "signal $it%" }).joinToString(" · "),
                    color = Melon.sage, fontSize = 13.sp,
                )
                st.ip?.let { ip -> IpRow(ip, st.user) }
            }
            else -> {
                Text("NOT CONNECTED", color = Melon.amber, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 2.sp)
                Text("Pick a network below.", color = Melon.cream, fontSize = 16.sp)
            }
        }
    }
}

/** The pedal's IPv4 address, big, with the ssh command; tap to copy it (for SSH from a computer). */
@Composable
private fun IpRow(ip: String, user: String?) {
    val clipboard = LocalClipboardManager.current
    var copied by remember { mutableStateOf(false) }
    val ssh = if (user.isNullOrEmpty()) "ssh $ip" else "ssh $user@$ip"
    if (copied) {
        LaunchedEffect(Unit) {
            delay(2000)
            copied = false
        }
    }
    Column(
        Modifier
            .fillMaxWidth()
            .padding(top = 8.dp)
            .background(Melon.surfaceHigh, RoundedCornerShape(6.dp))
            .clickable {
                clipboard.setText(AnnotatedString(ssh))
                copied = true
            }
            .padding(horizontal = 10.dp, vertical = 6.dp),
    ) {
        Text("IPv4 ADDRESS", color = Melon.sage, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 2.sp)
        Text(ip, color = Melon.cream, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, fontFamily = FontFamily.Monospace)
        Text(
            if (copied) "Copied: $ssh" else "$ssh  ·  tap to copy",
            color = if (copied) Melon.lime else Melon.sage, fontSize = 12.sp, fontFamily = FontFamily.Monospace,
        )
    }
}

@Composable
private fun JoinDialog(t: JoinTarget, onDismiss: () -> Unit, onJoin: (String, String?) -> Unit) {
    var ssid by remember { mutableStateOf(t.ssid) }
    var password by remember { mutableStateOf("") }
    var show by remember { mutableStateOf(false) }
    val needsPassword = t.secure && !t.known && !t.hidden     // hidden: empty = open network
    val pwOk = password.isEmpty() && !needsPassword || password.length in 8..63
    val ssidOk = ssid.isNotBlank() && ssid.toByteArray().size <= 32

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Melon.surface,
        title = { Text(if (t.hidden) "Hidden network" else t.ssid, color = Melon.cream) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (t.hidden) {
                    OutlinedTextField(
                        value = ssid, onValueChange = { ssid = it.take(32) },
                        label = { Text("Network name (SSID)") }, singleLine = true,
                    )
                }
                if (t.secure || t.hidden) {
                    OutlinedTextField(
                        value = password, onValueChange = { password = it.take(63) },
                        label = { Text(if (t.known) "Password (empty = use saved)" else if (t.hidden) "Password (empty = open network)" else "Password") },
                        singleLine = true,
                        visualTransformation = if (show) VisualTransformation.None else PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                    )
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clickable { show = !show }) {
                        Checkbox(
                            checked = show, onCheckedChange = { show = it },
                            colors = CheckboxDefaults.colors(checkedColor = Melon.lime, checkmarkColor = Melon.ground),
                        )
                        Text("Show password", color = Melon.sage, fontSize = 14.sp)
                    }
                    if (password.isNotEmpty() && password.length < 8) {
                        Text("Wi-Fi passwords have at least 8 characters", color = Melon.amber, fontSize = 12.sp)
                    }
                } else {
                    Text("Open network, no password.", color = Melon.sage)
                }
            }
        },
        confirmButton = {
            Button(onClick = { onJoin(ssid.trim(), password.ifEmpty { null }) }, enabled = ssidOk && pwOk) { Text("Connect") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

private fun bars(signal: Int) = when {
    signal >= 70 -> "●●●●"
    signal >= 50 -> "●●●○"
    signal >= 30 -> "●●○○"
    else -> "●○○○"
}
