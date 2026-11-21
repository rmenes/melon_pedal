package com.melonaudio.pedal.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.melonaudio.pedal.data.ControlDef
import com.melonaudio.pedal.data.Kind
import kotlin.math.roundToInt

/**
 * One parameter: label + value on top, the right widget below.
 * Double-tap the label row to go back to the default (same as double push on the pedal).
 */
@OptIn(ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
@Composable
fun ControlCard(
    def: ControlDef,
    value: Float,
    knob: Int?,                // 1-4 when this parameter is on the pedal's knobs right now
    onChange: (Float) -> Unit,
    onReset: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp)
            .background(Melon.surface, RoundedCornerShape(8.dp))
            .border(1.dp, if (knob != null) Melon.lime.copy(alpha = 0.5f) else Melon.surface, RoundedCornerShape(8.dp))
            .padding(horizontal = 14.dp, vertical = 10.dp),
    ) {
        Row(
            Modifier.fillMaxWidth().pointerInput(def) { detectTapGestures(onDoubleTap = { onReset() }) },
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (knob != null) {
                Box(
                    Modifier.size(22.dp).border(1.5.dp, Melon.lime, CircleShape),
                    contentAlignment = Alignment.Center,
                ) { Text("$knob", color = Melon.lime, fontSize = 11.sp, fontWeight = FontWeight.Bold) }
                Spacer(Modifier.width(8.dp))
            }
            Text(
                def.label, color = Melon.sage, fontSize = 14.sp,
                maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
            )
            Text(def.format(value), color = Melon.lime, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        }

        when (def.kind) {
            Kind.TOGGLE -> Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                Switch(
                    checked = def.isOn(value),
                    onCheckedChange = { onChange(if (it) def.max else def.min) },
                    colors = SwitchDefaults.colors(
                        checkedThumbColor = Melon.ground, checkedTrackColor = Melon.lime,
                        uncheckedThumbColor = Melon.sage, uncheckedTrackColor = Melon.ground,
                        uncheckedBorderColor = Melon.line,
                    ),
                )
            }

            Kind.ENUM -> if (def.options.size <= 5) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    val sel = def.nearestOption(value)
                    def.options.forEachIndexed { i, o ->
                        FilterChip(
                            selected = i == sel,
                            onClick = { onChange(o.value) },
                            label = { Text(o.label) },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = Melon.lime, selectedLabelColor = Melon.ground,
                                labelColor = Melon.cream,
                            ),
                        )
                    }
                }
            } else {
                var open by remember { mutableStateOf(false) }
                Box {
                    OutlinedButton(onClick = { open = true }) { Text(def.format(value) + "  ▾", color = Melon.cream) }
                    DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                        def.options.forEach { o ->
                            DropdownMenuItem(text = { Text(o.label) }, onClick = { onChange(o.value); open = false })
                        }
                    }
                }
            }

            Kind.FLOAT, Kind.INT -> {
                val span = (def.max - def.min).roundToInt()
                val steps = if (def.kind == Kind.INT && !def.log && span in 2..40) span - 1 else 0
                Slider(
                    value = def.toNorm(value),
                    onValueChange = { n -> onChange(def.fromNorm(n)) },
                    steps = steps,
                    colors = SliderDefaults.colors(
                        thumbColor = Melon.lime, activeTrackColor = Melon.lime,
                        inactiveTrackColor = Melon.line,
                        activeTickColor = Melon.ground, inactiveTickColor = Melon.sage,
                    ),
                )
            }
        }
    }
}

/** GraphicEQ-style band graph; the bands on the pedal's knobs are highlighted. */
@Composable
fun BandGraph(values: List<Float>, min: Float, max: Float, highlight: Set<Int>) {
    Canvas(
        Modifier
            .fillMaxWidth()
            .height(110.dp)
            .background(Melon.surface, RoundedCornerShape(8.dp))
            .padding(10.dp),
    ) {
        if (values.isEmpty() || max <= min) return@Canvas
        val zeroY = size.height * (max / (max - min))
        drawLine(Melon.line, Offset(0f, zeroY), Offset(size.width, zeroY), strokeWidth = 2f)
        val slot = size.width / values.size
        val barW = (slot * 0.6f).coerceAtLeast(2f)
        values.forEachIndexed { i, v ->
            val y = size.height * ((max - v.coerceIn(min, max)) / (max - min))
            val top = minOf(y, zeroY)
            val h = maxOf(kotlin.math.abs(zeroY - y), 2f)
            drawRoundRect(
                color = if (i in highlight) Melon.lime else Melon.sage.copy(alpha = 0.55f),
                topLeft = Offset(i * slot + (slot - barW) / 2, top),
                size = Size(barW, h),
                cornerRadius = CornerRadius(2f, 2f),
            )
        }
    }
}
