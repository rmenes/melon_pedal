package com.melonaudio.pedal.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.melonaudio.pedal.PedalViewModel
import com.melonaudio.pedal.data.ChainBlock
import com.melonaudio.pedal.data.Dsp
import com.melonaudio.pedal.data.PedalState
import com.melonaudio.pedal.data.PluginInfo
import java.util.Locale

/*
 * Multi-FX chain (docs/multifx-design.md §5): the strip under the preset band, the Chain tab
 * and the "Add block" list. The pedal decides; the app only asks (add_block, remove_block,
 * move_block, block_on, select_block) and shows the state the pedal sends back.
 */

const val MAX_BLOCKS = 10

/** Default chain order, same as melon-pedald's chain.CATEGORY_ORDER (unknown plugins sit before Delay). */
private val CATEGORY_ORDER = listOf("gate", "pitch", "dynamics", "drive", "amp", "cab", "mod", "delay", "reverb", "eq")

private fun categoryRank(cat: String): Float = when (cat) {
    "tuner" -> -1f
    in CATEGORY_ORDER -> CATEGORY_ORDER.indexOf(cat).toFloat()
    else -> CATEGORY_ORDER.indexOf("delay") - 0.5f
}

private fun pct(v: Float): String = String.format(Locale.US, "%.0f%%", v)

/** Colour of a DSP number: normal below 60 %, amber up to the limit, red at the limit (as on the LCD). */
private fun dspColor(v: Float, limit: Float): Color = when {
    v >= limit -> Melon.bypass
    v >= 60f -> Melon.amber
    else -> Melon.sage
}

// ---------------------------------------------------------------------------------- strip

/** One chip per block, like the LCD: lit = on, dim = off, cream frame = on the knobs. Tap = select. */
@Composable
fun ChainStrip(s: PedalState, onSelect: (Int) -> Unit) {
    if (s.chain.isEmpty()) return
    Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            s.chain.forEach { b ->
                BlockChip(b, selected = b.b == s.cur, modifier = Modifier.weight(1f)) { onSelect(b.b) }
            }
            // keep chips at a readable width when the chain is short
            if (s.chain.size < 5) Spacer(Modifier.weight((5 - s.chain.size).toFloat()))
        }
        s.dsp?.let { d ->
            Text(
                "DSP ${pct(d.shown)}", color = dspColor(d.shown, d.limit), fontSize = 12.sp,
                fontWeight = FontWeight.Bold, modifier = Modifier.padding(start = 8.dp),
            )
        }
    }
}

@Composable
private fun BlockChip(b: ChainBlock, selected: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val shape = RoundedCornerShape(5.dp)
    val base = if (b.on) modifier.background(Melon.surface, shape) else modifier.border(1.dp, Melon.line, shape)
    val framed = if (selected) base.border(2.dp, Melon.cream, shape) else base
    Box(
        framed.height(30.dp).clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            b.tag, fontSize = 11.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Clip,
            color = when {
                b.on && selected -> Melon.cream
                b.on -> Melon.lime
                selected -> Melon.sage
                else -> Melon.dim
            },
        )
    }
}

// ---------------------------------------------------------------------------------- tab

@Composable
fun ChainTab(s: PedalState, vm: PedalViewModel, onEdit: (Int) -> Unit) {
    var adding by remember { mutableStateOf(false) }
    LazyColumn(Modifier.fillMaxSize()) {
        item { DspCard(s.dsp, s.chain.size) }
        items(s.chain, key = { "${it.b}/${it.uri}" }) { b ->
            BlockRow(
                b, selected = b.b == s.cur, count = s.chain.size,
                onEdit = { onEdit(b.b) },
                onOn = { on -> vm.setBlockOn(b.b, on) },
                onUp = { vm.moveBlock(b.b, b.b - 1) },
                onDown = { vm.moveBlock(b.b, b.b + 1) },
                onRemove = { vm.removeBlock(b.b) },
            )
        }
        item {
            if (s.chain.size < MAX_BLOCKS) {
                Button(onClick = { adding = true }, modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp)) {
                    Text("+ Add block")
                }
            } else {
                Text("The chain is full ($MAX_BLOCKS blocks).", color = Melon.sage, fontSize = 13.sp,
                    modifier = Modifier.padding(vertical = 12.dp))
            }
            Text(
                "Tap a block to edit it (it goes on the pedal's knobs). A new block goes to its place in the " +
                    "chain: Gate → Pitch/Synth → Comp → Drive → Amp → Cab → Mod → Delay → Reverb → EQ.",
                color = Melon.dim, fontSize = 12.sp, modifier = Modifier.padding(bottom = 24.dp),
            )
        }
    }
    if (adding) {
        AddBlockDialog(s, onDismiss = { adding = false }) { plugin ->
            vm.addBlock(plugin)
            adding = false
        }
    }
}

@Composable
private fun DspCard(d: Dsp?, blocks: Int) {
    Column(
        Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 6.dp)
            .background(Melon.surface, RoundedCornerShape(8.dp)).padding(12.dp),
    ) {
        if (d == null) {
            Text("DSP: no numbers from the pedal yet", color = Melon.sage, fontSize = 13.sp)
            return@Column
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("DSP", color = Melon.sage, fontSize = 12.sp, letterSpacing = 2.sp, modifier = Modifier.weight(1f))
            Text(pct(d.shown), color = dspColor(d.shown, d.limit), fontSize = 22.sp, fontWeight = FontWeight.Bold)
            Text("  of ${pct(d.limit)}", color = Melon.sage, fontSize = 13.sp)
        }
        Spacer(Modifier.height(6.dp))
        // bar: 0..100 %, the limit is the end of the green/amber zone
        Box(Modifier.fillMaxWidth().height(10.dp).background(Melon.line, RoundedCornerShape(5.dp))) {
            Box(
                Modifier.fillMaxWidth((d.shown / 100f).coerceIn(0.02f, 1f)).fillMaxHeight()
                    .background(dspColor(d.shown, d.limit).let { if (it == Melon.sage) Melon.lime else it }, RoundedCornerShape(5.dp)),
            )
        }
        Spacer(Modifier.height(6.dp))
        val live = if (d.load != null) "live ${pct(d.load)} · peak ${pct(d.peak ?: d.load)} · xruns ${d.xruns ?: 0}" else "no live meter"
        Text(
            "predicted ${pct(d.predicted)} for $blocks block${if (blocks == 1) "" else "s"} · $live",
            color = if ((d.xruns ?: 0) > 0) Melon.amber else Melon.sage, fontSize = 12.sp,
        )
    }
}

@Composable
private fun BlockRow(
    b: ChainBlock,
    selected: Boolean,
    count: Int,
    onEdit: () -> Unit,
    onOn: (Boolean) -> Unit,
    onUp: () -> Unit,
    onDown: () -> Unit,
    onRemove: () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 3.dp)
            .background(if (selected) Melon.rind else Melon.surface, RoundedCornerShape(6.dp))
            .clickable(onClick = onEdit)
            .padding(start = 10.dp, end = 4.dp, top = 6.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("${b.b + 1}", color = if (selected) Melon.lime else Melon.sage, fontSize = 15.sp,
            fontWeight = FontWeight.Bold, modifier = Modifier.width(22.dp))
        Column(Modifier.weight(1f)) {
            Text(
                b.name.removePrefix("Melon "), color = if (b.on) Melon.cream else Melon.dim, fontSize = 16.sp,
                maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
            Text(
                "${b.tag} · ${pct(b.cost)}" + if (selected) " · on the knobs" else "",
                color = if (selected) Melon.lime else Melon.sage, fontSize = 12.sp, maxLines = 1,
            )
        }
        Switch(
            checked = b.on, onCheckedChange = onOn,
            colors = SwitchDefaults.colors(checkedTrackColor = Melon.lime, checkedThumbColor = Melon.ground),
        )
        SmallAction("▲", enabled = b.b > 0, onClick = onUp)
        SmallAction("▼", enabled = b.b < count - 1, onClick = onDown)
        SmallAction("✕", enabled = count > 1, onClick = onRemove)
    }
}

@Composable
private fun SmallAction(text: String, enabled: Boolean, onClick: () -> Unit) {
    Box(
        Modifier.width(34.dp).height(40.dp).clickable(enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, color = if (enabled) Melon.cream else Melon.line, fontSize = 16.sp, textAlign = TextAlign.Center)
    }
}

// ---------------------------------------------------------------------------------- add block

@Composable
private fun AddBlockDialog(s: PedalState, onDismiss: () -> Unit, onAdd: (Int) -> Unit) {
    val list = s.plugins.filter { it.cat != "tuner" }.sortedWith(compareBy({ categoryRank(it.cat) }, { it.name }))
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Melon.surface,
        title = {
            Column {
                Text("Add block", color = Melon.cream)
                s.dsp?.let {
                    Text("DSP now ${pct(it.shown)} · limit ${pct(it.limit)}", color = Melon.sage, fontSize = 13.sp)
                }
            }
        },
        text = {
            LazyColumn(Modifier.fillMaxWidth().heightIn(max = 460.dp)) {
                items(list, key = { it.uri }) { p -> AddRow(p, s.dsp) { onAdd(p.index) } }
            }
        },
        confirmButton = {},
        dismissButton = { TextButton(onClick = onDismiss) { Text("Close") } },
    )
}

@Composable
private fun AddRow(p: PluginInfo, dsp: Dsp?, onClick: () -> Unit) {
    val cost = p.cost
    val fits = cost == null || dsp == null || dsp.fits(cost)
    val lightFits = p.costLight != null && dsp != null && dsp.fits(p.costLight)
    // Melon NAM starts without a model (almost free); the cost comes when a model is chosen.
    val canAdd = fits || lightFits
    val costText = when {
        cost == null -> "?"
        p.costLight != null -> "${pct(cost)} (Light ${pct(p.costLight)})"
        else -> pct(cost)
    }
    Row(
        Modifier.fillMaxWidth().padding(vertical = 2.dp)
            .background(Melon.ground, RoundedCornerShape(6.dp))
            .clickable(enabled = canAdd, onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(p.name.removePrefix("Melon "), color = if (canAdd) Melon.cream else Melon.dim, fontSize = 16.sp)
            Text("${p.tag.ifEmpty { "FX" }} · DSP $costText", color = Melon.sage, fontSize = 12.sp)
        }
        when {
            !canAdd -> Note("won't fit", Melon.bypass)
            !fits -> Note("Light only", Melon.amber)
        }
    }
}

@Composable
private fun Note(text: String, color: Color) {
    Text(
        text, color = Melon.ground, fontSize = 11.sp, fontWeight = FontWeight.Bold,
        modifier = Modifier.background(color, RoundedCornerShape(4.dp)).padding(horizontal = 6.dp, vertical = 2.dp),
    )
}
