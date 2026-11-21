package com.melonaudio.pedal.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.TabRowDefaults
import androidx.compose.material3.TabRowDefaults.tabIndicatorOffset
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.melonaudio.pedal.PedalViewModel
import com.melonaudio.pedal.data.PedalState
import com.melonaudio.pedal.data.Protocol
import kotlinx.coroutines.delay

@Composable
fun PedalScreen(vm: PedalViewModel) {
    val s by vm.state.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var saving by remember { mutableStateOf(false) }

    if (!s.synced || s.plugin == null) {
        Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
            CircularProgressIndicator(color = Melon.lime)
            Spacer(Modifier.height(12.dp))
            Text("Reading the pedal…", color = Melon.sage)
        }
        return
    }

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        TopBar(s.pedalName) { vm.disconnect() }
        PresetBand(s)
        Spacer(Modifier.height(10.dp))
        BypassButton(s.bypass) { vm.toggleBypass() }
        if (s.mode != "play") {
            Text(
                if (s.mode == "save") "The pedal is on its save screen" else "The pedal is in its preset browser",
                color = Melon.amber, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp),
            )
        }
        Spacer(Modifier.height(8.dp))
        TabRow(
            selectedTabIndex = tab,
            containerColor = Melon.ground,
            contentColor = Melon.cream,
            indicator = { pos ->
                TabRowDefaults.SecondaryIndicator(Modifier.tabIndicatorOffset(pos[tab]), color = Melon.lime)
            },
        ) {
            listOf("Sound", "Presets", "Plugins").forEachIndexed { i, title ->
                Tab(
                    selected = tab == i, onClick = { tab = i },
                    text = { Text(title, color = if (tab == i) Melon.cream else Melon.sage) },
                )
            }
        }
        Box(Modifier.weight(1f)) {
            when (tab) {
                0 -> SoundTab(s, vm)
                1 -> PresetsTab(s, vm, onSave = { saving = true })
                else -> PluginsTab(s, vm)
            }
        }
        s.error?.let { msg ->
            LaunchedEffect(msg) {
                delay(4000)
                vm.clearError()
            }
            Text(
                msg, color = Melon.ground, fontSize = 13.sp,
                modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)
                    .background(Melon.amber, RoundedCornerShape(6.dp)).padding(10.dp),
            )
        }
    }

    if (saving) SaveDialog(s, onDismiss = { saving = false }) { slot, name ->
        vm.savePreset(slot, name)
        saving = false
    }
}

@Composable
private fun TopBar(name: String, onDisconnect: () -> Unit) {
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).background(Melon.lime, CircleShape))
        Spacer(Modifier.width(8.dp))
        Text(name, color = Melon.sage, fontSize = 13.sp, modifier = Modifier.weight(1f))
        TextButton(onClick = onDisconnect) { Text("Disconnect", color = Melon.sage, fontSize = 13.sp) }
    }
}

@Composable
private fun PresetBand(s: PedalState) {
    val preset = s.slot?.let { s.presets.getOrNull(it) }
    Row(
        Modifier.fillMaxWidth().background(Melon.surface, RoundedCornerShape(8.dp)).padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier.size(52.dp).background(if (preset != null) Melon.lime else Melon.line, RoundedCornerShape(6.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                if (preset != null) s.slotLabel(s.slot!!) else "--",
                color = Melon.ground, fontWeight = FontWeight.Bold, fontSize = 15.sp,
            )
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(
                preset?.name ?: s.plugin!!.name, color = Melon.cream, fontSize = 22.sp,
                fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
            Text(
                if (preset != null) s.plugin!!.name else "not saved",
                color = Melon.sage, fontSize = 13.sp, maxLines = 1,
            )
        }
        if (s.edited) {
            Text(
                "EDITED", color = Melon.ground, fontSize = 11.sp, fontWeight = FontWeight.Bold,
                modifier = Modifier.background(Melon.amber, RoundedCornerShape(4.dp)).padding(horizontal = 6.dp, vertical = 2.dp),
            )
        }
    }
}

@Composable
private fun BypassButton(bypassed: Boolean, onClick: () -> Unit) {
    val bg = if (bypassed) Melon.bypass else Melon.ground
    Box(
        Modifier
            .fillMaxWidth()
            .height(56.dp)
            .background(bg, RoundedCornerShape(8.dp))
            .border(2.dp, if (bypassed) Melon.bypass else Melon.lime, RoundedCornerShape(8.dp))
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                if (bypassed) "BYPASS" else "EFFECT ON",
                color = if (bypassed) Color.White else Melon.lime, fontSize = 20.sp, fontWeight = FontWeight.Bold,
                letterSpacing = 2.sp,
            )
            Text(
                if (bypassed) "dry signal · tap to turn on" else "tap to bypass",
                color = if (bypassed) Color.White.copy(alpha = 0.8f) else Melon.sage, fontSize = 11.sp,
            )
        }
    }
}

@Composable
private fun SoundTab(s: PedalState, vm: PedalViewModel) {
    val plugin = s.plugin ?: return
    val controls = plugin.controls
    LazyColumn(Modifier.fillMaxSize()) {
        if (plugin.bands.isNotEmpty()) {
            item {
                val onKnobs = (s.page * 4 until s.page * 4 + 4).toSet()
                val first = plugin.bands.first()
                BandGraph(
                    values = plugin.bands.map { s.values.getOrElse(it) { 0f } },
                    min = controls[first].min, max = controls[first].max,
                    highlight = plugin.bands.indices.filter { plugin.bands[it] in onKnobs }.toSet(),
                )
                Spacer(Modifier.height(4.dp))
            }
        }
        if (controls.isEmpty()) {
            item { Text("This plugin has no parameters.", color = Melon.sage, modifier = Modifier.padding(16.dp)) }
        }
        for (page in 0 until s.pages) {
            val from = page * 4
            if (from >= controls.size) break
            item(key = "page$page") {
                Row(Modifier.fillMaxWidth().padding(top = 12.dp, bottom = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("PAGE ${page + 1}", color = Melon.sage, fontSize = 12.sp, letterSpacing = 2.sp, modifier = Modifier.weight(1f))
                    if (page == s.page) {
                        Text("ON THE KNOBS", color = Melon.lime, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    } else if (s.mode == "play") {
                        Text(
                            "put on knobs", color = Melon.sage, fontSize = 12.sp,
                            modifier = Modifier.clickable { vm.putPageOnKnobs(page) }.padding(4.dp),
                        )
                    }
                }
            }
            items((from until minOf(from + 4, controls.size)).toList(), key = { "c$it-${plugin.gen}" }) { i ->
                ControlCard(
                    def = controls[i],
                    value = s.values.getOrElse(i) { controls[i].default },
                    knob = if (page == s.page) i - from + 1 else null,
                    onChange = { v -> vm.setValue(i, v) },
                    onReset = { vm.resetValue(i) },
                )
            }
        }
        item { Spacer(Modifier.height(24.dp)) }
    }
}

@Composable
private fun PresetsTab(s: PedalState, vm: PedalViewModel, onSave: () -> Unit) {
    val banks = (s.presets.size + s.bankSize - 1) / s.bankSize
    var bank by remember { mutableIntStateOf((s.slot ?: 0) / s.bankSize) }
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            for (b in 0 until banks) {
                BankChip("Bank ${b + 1}", b == bank) { bank = b }
            }
        }
        LazyColumn(Modifier.weight(1f)) {
            items((bank * s.bankSize until minOf((bank + 1) * s.bankSize, s.presets.size)).toList()) { slot ->
                val p = s.presets[slot]
                val loaded = slot == s.slot
                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(vertical = 3.dp)
                        .background(if (loaded) Melon.rind else Melon.surface, RoundedCornerShape(6.dp))
                        .clickable(enabled = p != null) { vm.loadPreset(slot) }
                        .padding(horizontal = 12.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("%02d".format(slot % s.bankSize + 1), color = Melon.sage, fontSize = 14.sp, modifier = Modifier.width(32.dp))
                    Column(Modifier.weight(1f)) {
                        Text(p?.name ?: "— empty —", color = if (p != null) Melon.cream else Melon.dim, fontSize = 17.sp)
                        if (p != null) Text(p.pluginName.removePrefix("Melon "), color = Melon.sage, fontSize = 12.sp)
                    }
                    if (loaded) Text("▶", color = Melon.lime, fontSize = 16.sp)
                }
            }
        }
        Button(onClick = onSave, modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp)) {
            Text("Save current sound…")
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun BankChip(text: String, selected: Boolean, onClick: () -> Unit) {
    FilterChip(
        selected = selected, onClick = onClick, label = { Text(text) },
        colors = FilterChipDefaults.filterChipColors(
            selectedContainerColor = Melon.lime, selectedLabelColor = Melon.ground, labelColor = Melon.cream,
        ),
    )
}

@Composable
private fun PluginsTab(s: PedalState, vm: PedalViewModel) {
    LazyColumn(Modifier.fillMaxSize().padding(top = 8.dp)) {
        items(s.plugins, key = { it.uri }) { p ->
            val loaded = p.index == s.plugin?.index
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(vertical = 3.dp)
                    .background(if (loaded) Melon.rind else Melon.surface, RoundedCornerShape(6.dp))
                    .clickable(enabled = !loaded) { vm.loadPlugin(p.index) }
                    .padding(horizontal = 12.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(p.name, color = Melon.cream, fontSize = 17.sp)
                    Text("${p.count} parameters", color = Melon.sage, fontSize = 12.sp)
                }
                if (loaded) {
                    Text(
                        "LOADED", color = Melon.ground, fontSize = 11.sp, fontWeight = FontWeight.Bold,
                        modifier = Modifier.background(Melon.lime, RoundedCornerShape(4.dp)).padding(horizontal = 6.dp, vertical = 2.dp),
                    )
                }
            }
        }
        item {
            Text(
                "Loading a plugin switches the pedal to dry signal for a moment.",
                color = Melon.dim, fontSize = 12.sp, modifier = Modifier.padding(vertical = 12.dp),
            )
        }
    }
}

@Composable
private fun SaveDialog(s: PedalState, onDismiss: () -> Unit, onSave: (Int, String) -> Unit) {
    val current = s.slot?.let { s.presets.getOrNull(it) }
    val firstEmpty = s.presets.indexOfFirst { it == null }
    var slot by remember { mutableIntStateOf(s.slot ?: if (firstEmpty >= 0) firstEmpty else 0) }
    var name by remember { mutableStateOf(current?.name ?: s.plugin?.name?.removePrefix("Melon ").orEmpty()) }
    val target = s.presets.getOrNull(slot)

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Melon.surface,
        title = { Text("Save preset", color = Melon.cream) },
        text = {
            Column {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = Protocol.cleanName(it) },
                    label = { Text("Name (max ${Protocol.NAME_LEN})") },
                    singleLine = true,
                )
                Spacer(Modifier.height(16.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = { slot = (slot - 1 + s.presets.size) % s.presets.size }) { Text("◀", fontSize = 18.sp) }
                    Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("Slot ${s.slotLabel(slot)}", color = Melon.cream, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                        Text(
                            if (target == null) "empty" else "replaces ${target.name}",
                            color = if (target == null || slot == s.slot) Melon.sage else Melon.amber, fontSize = 12.sp,
                        )
                    }
                    TextButton(onClick = { slot = (slot + 1) % s.presets.size }) { Text("▶", fontSize = 18.sp) }
                }
            }
        },
        confirmButton = { Button(onClick = { onSave(slot, name) }) { Text("Save") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
