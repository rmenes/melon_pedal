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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.melonaudio.pedal.PedalViewModel
import com.melonaudio.pedal.data.AudioIo
import com.melonaudio.pedal.data.IoOption

/**
 * Which inputs and outputs of the audio interface the pedal uses (for interfaces with many
 * channels, like the Audient Sono). A change is instant on the pedal (only the routing changes)
 * and the pedal remembers it for that interface.
 */
@Composable
fun AudioScreen(a: AudioIo?, vm: PedalViewModel, onClose: () -> Unit) {
    var tab by remember { mutableStateOf("in") }

    BackHandler(onBack = onClose)
    LaunchedEffect(Unit) { vm.audioRefresh() }

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onClose) { Text("‹ Back", color = Melon.sage) }
            Text("Audio inputs & outputs", color = Melon.cream, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
        }
        if (a == null) {
            Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(color = Melon.lime)
                Spacer(Modifier.width(10.dp))
                Text("Reading the interface…", color = Melon.sage)
            }
            return@Column
        }

        Column(
            Modifier.fillMaxWidth().background(Melon.surface, RoundedCornerShape(8.dp)).padding(12.dp),
        ) {
            Text(a.card, color = Melon.cream, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
            if (a.info.isNotEmpty()) Text(a.info, color = Melon.sage, fontSize = 12.sp)
            Spacer(Modifier.height(6.dp))
            Text(
                "Using ${label(a.inputs, a.input)} → ${label(a.outputs, a.output)}",
                color = Melon.lime, fontSize = 14.sp,
            )
        }

        Row(Modifier.fillMaxWidth().padding(top = 12.dp, bottom = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Chip("Input", tab == "in", Modifier.weight(1f)) { tab = "in" }
            Chip("Output", tab == "out", Modifier.weight(1f)) { tab = "out" }
        }
        Text(
            if (tab == "in") "Mono: one input feeds both sides of the chain. Stereo: a pair of inputs."
            else "Stereo: a pair of outputs. Mono: the left side of the chain only.",
            color = Melon.dim, fontSize = 12.sp, modifier = Modifier.padding(bottom = 6.dp),
        )

        val opts = if (tab == "in") a.inputs else a.outputs
        val current = if (tab == "in") a.input else a.output
        LazyColumn(Modifier.weight(1f)) {
            items(opts, key = { tab + it.id }) { o ->
                OptionRow(o, o.id == current) {
                    if (tab == "in") vm.setAudio(input = o.id) else vm.setAudio(output = o.id)
                }
            }
        }
        Text(
            "Turn off direct monitoring / loopback on the interface itself, so only the pedal's sound is heard.",
            color = Melon.dim, fontSize = 12.sp, modifier = Modifier.padding(vertical = 8.dp),
        )
    }
}

private fun label(opts: List<IoOption>, id: String) = opts.firstOrNull { it.id == id }?.label ?: id

@Composable
private fun Chip(text: String, on: Boolean, modifier: Modifier, onClick: () -> Unit) {
    Text(
        text, color = if (on) Melon.ground else Melon.cream, fontSize = 15.sp, fontWeight = FontWeight.SemiBold,
        modifier = modifier
            .background(if (on) Melon.lime else Melon.surface, RoundedCornerShape(6.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 10.dp),
        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
    )
}

@Composable
private fun OptionRow(o: IoOption, selected: Boolean, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp)
            .background(if (selected) Melon.rind else Melon.surface, RoundedCornerShape(6.dp))
            .clickable(enabled = !selected, onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(o.label, color = Melon.cream, fontSize = 16.sp, modifier = Modifier.weight(1f))
        Text(if (o.stereo) "stereo" else "mono", color = Melon.sage, fontSize = 12.sp)
        if (selected) {
            Spacer(Modifier.width(10.dp))
            Text("✓", color = Melon.lime, fontSize = 16.sp)
        }
    }
}
