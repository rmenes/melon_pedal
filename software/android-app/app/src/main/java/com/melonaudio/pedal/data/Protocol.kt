package com.melonaudio.pedal.data

import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale
import kotlin.math.abs
import kotlin.math.ln
import kotlin.math.pow
import kotlin.math.roundToInt

/*
 * melon-pedald remote API (see software/melon-pedald/melon_pedald/remote.py).
 * One JSON object per line. App -> pedal: {"op": ...}. Pedal -> app: {"ev": ...}.
 */

enum class Kind { FLOAT, INT, TOGGLE, ENUM }

data class Choice(val value: Float, val label: String)

data class ControlDef(
    val label: String,
    val min: Float,
    val max: Float,
    val default: Float,
    val unit: String,
    val kind: Kind,
    val log: Boolean,
    val options: List<Choice>,
) {
    /** 0..1 slider position for a value (log scale for frequencies etc.). */
    fun toNorm(v: Float): Float {
        if (max == min) return 0f
        val n = if (log && min > 0f && v > 0f) (ln(v / min) / ln(max / min)) else (v - min) / (max - min)
        return n.coerceIn(0f, 1f)
    }

    fun fromNorm(n: Float): Float {
        val c = n.coerceIn(0f, 1f)
        val v = if (log && min > 0f) min * (max / min).pow(c) else min + c * (max - min)
        return if (kind == Kind.INT) v.roundToInt().toFloat() else v
    }

    fun nearestOption(v: Float): Int =
        options.indices.minByOrNull { abs(options[it].value - v) } ?: 0

    fun isOn(v: Float) = v >= (min + max) / 2f

    /** Same text as the pedal's LCD (catalog.Control.format). */
    fun format(v: Float): String {
        if (kind == Kind.ENUM && options.isNotEmpty()) return options[nearestOption(v)].label
        if (kind == Kind.TOGGLE) return if (isOn(v)) "On" else "Off"
        var value = v
        var u = unit
        if (u == "Hz" && abs(value) >= 1000f) {
            value /= 1000f; u = "kHz"
        }
        var txt = when {
            kind == Kind.INT || abs(value) >= 100f -> String.format(Locale.US, "%.0f", value)
            abs(value) >= 10f -> String.format(Locale.US, "%.1f", value)
            else -> String.format(Locale.US, "%.2f", value)
        }
        if (txt == "-0" || txt == "-0.0" || txt == "-0.00") txt = txt.substring(1)
        return "$txt $u".trim()
    }
}

data class PluginInfo(val index: Int, val name: String, val uri: String, val count: Int)

data class PresetInfo(val name: String, val pluginName: String)

data class LoadedPlugin(
    val gen: Int,
    val index: Int,
    val name: String,
    val uri: String,
    val controls: List<ControlDef>,
) {
    /** Ten or more dB controls with the same range around 0 (e.g. Melon GraphicEQ): draw a band graph. */
    val bands: List<Int> by lazy {
        val db = controls.indices.filter { controls[it].unit == "dB" && controls[it].kind == Kind.FLOAT }
        if (db.size < 10) return@lazy emptyList()
        val range = db.groupingBy { controls[it].min to controls[it].max }.eachCount().maxByOrNull { it.value }
        if (range == null || range.value < 10 || range.key.first >= 0f || range.key.second <= 0f) emptyList()
        else db.filter { controls[it].min to controls[it].max == range.key }
    }
}

data class PedalState(
    val pedalName: String = "Melon Pedal",
    val plugins: List<PluginInfo> = emptyList(),
    val presets: List<PresetInfo?> = List(24) { null },
    val bankSize: Int = 6,
    val plugin: LoadedPlugin? = null,
    val values: List<Float> = emptyList(),
    val slot: Int? = null,
    val edited: Boolean = false,
    val bypass: Boolean = false,
    val page: Int = 0,
    val pages: Int = 1,
    val mode: String = "play",
    val synced: Boolean = false,          // got the first full state after connecting
    val error: String? = null,
) {
    fun slotLabel(slot: Int) = "${slot / bankSize + 1}-${"%02d".format(slot % bankSize + 1)}"
}

object Protocol {
    const val NAME_LEN = 16
    const val CHARSET = " ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.'&!#+"

    private fun op(name: String) = JSONObject().put("op", name)

    fun hello() = op("hello").put("app", "android").put("proto", 1).toString()
    fun set(gen: Int, index: Int, value: Float) =
        op("set").put("gen", gen).put("i", index).put("v", value.toDouble()).toString()
    fun bypass(on: Boolean) = op("bypass").put("on", on).toString()
    fun page(n: Int) = op("page").put("n", n).toString()
    fun loadPlugin(i: Int) = op("load_plugin").put("i", i).toString()
    fun loadPreset(slot: Int) = op("load_preset").put("slot", slot).toString()
    fun savePreset(slot: Int, name: String) = op("save_preset").put("slot", slot).put("name", name).toString()

    fun cleanName(s: String) = s.filter { it in CHARSET }.take(NAME_LEN)

    private fun parseControl(o: JSONObject): ControlDef {
        val opts = o.optJSONArray("o")?.let { arr ->
            (0 until arr.length()).map { i ->
                val pair = arr.getJSONArray(i)
                Choice(pair.getDouble(0).toFloat(), pair.getString(1))
            }
        } ?: emptyList()
        return ControlDef(
            label = o.optString("l"),
            min = o.optDouble("min", 0.0).toFloat(),
            max = o.optDouble("max", 1.0).toFloat(),
            default = o.optDouble("d", 0.0).toFloat(),
            unit = o.optString("u", ""),
            kind = when (o.optString("k")) {
                "int" -> Kind.INT
                "toggle" -> Kind.TOGGLE
                "enum" -> Kind.ENUM
                else -> Kind.FLOAT
            },
            log = o.optBoolean("log", false),
            options = opts,
        )
    }

    private fun floats(arr: JSONArray?): List<Float> =
        if (arr == null) emptyList() else (0 until arr.length()).map { arr.optDouble(it, 0.0).toFloat() }

    /**
     * Applies one event line to the state.
     * [keepLocal] says which parameter indexes the user is moving right now: incoming
     * values for them are ignored so the slider doesn't jump back while dragging.
     */
    fun apply(s: PedalState, line: String, keepLocal: (Int) -> Boolean): PedalState {
        val o = try { JSONObject(line) } catch (e: Exception) { return s }
        return when (o.optString("ev")) {
            "hello" -> s.copy(pedalName = o.optString("name", s.pedalName))
            "plugins" -> {
                val arr = o.optJSONArray("list") ?: JSONArray()
                s.copy(plugins = (0 until arr.length()).map {
                    val p = arr.getJSONObject(it)
                    PluginInfo(p.optInt("i", it), p.optString("name"), p.optString("uri"), p.optInt("n"))
                })
            }
            "presets" -> {
                val arr = o.optJSONArray("slots") ?: JSONArray()
                s.copy(
                    bankSize = o.optInt("bank_size", 6),
                    presets = (0 until arr.length()).map {
                        if (arr.isNull(it)) null
                        else arr.getJSONObject(it).let { p -> PresetInfo(p.optString("name"), p.optString("plugin_name")) }
                    },
                )
            }
            "plugin" -> {
                val arr = o.optJSONArray("controls") ?: JSONArray()
                val controls = (0 until arr.length()).map { parseControl(arr.getJSONObject(it)) }
                s.copy(
                    plugin = LoadedPlugin(o.optInt("gen"), o.optInt("i"), o.optString("name"), o.optString("uri"), controls),
                    values = controls.map { it.default },
                )
            }
            "state" -> {
                if (s.plugin != null && o.optInt("gen") != s.plugin.gen) return s
                val incoming = floats(o.optJSONArray("values"))
                val merged = incoming.mapIndexed { i, v -> if (keepLocal(i) && i < s.values.size) s.values[i] else v }
                s.copy(
                    values = merged,
                    slot = if (o.isNull("slot")) null else o.optInt("slot"),
                    edited = o.optBoolean("edited"),
                    bypass = o.optBoolean("bypass"),
                    page = o.optInt("page"),
                    pages = o.optInt("pages", 1),
                    mode = o.optString("mode", "play"),
                    synced = true,
                )
            }
            "param" -> {
                val i = o.optInt("i", -1)
                if (s.plugin == null || o.optInt("gen") != s.plugin.gen || i !in s.values.indices || keepLocal(i)) s
                else s.copy(values = s.values.toMutableList().also { it[i] = o.optDouble("v").toFloat() })
            }
            "bypass" -> s.copy(bypass = o.optBoolean("on"))
            "error" -> s.copy(error = o.optString("msg"))
            else -> s
        }
    }
}
