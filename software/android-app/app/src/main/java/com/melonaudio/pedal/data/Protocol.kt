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
    /** "NAM" / "IR": Melon NAM / Melon Cab file control. The value is a position in the
     *  pedal's library; the app shows and picks the file by name instead (lib_list / set_file). */
    val lib: String? = null,
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

data class PluginInfo(
    val index: Int,
    val name: String,
    val uri: String,
    val count: Int,
    val cat: String = "",            // category: gate, pitch, dynamics, drive, amp, cab, mod, delay, reverb, eq, other
    val tag: String = "",            // short label as on the LCD chain strip ("DRIVE", "MOD", …)
    val cost: Float? = null,         // DSP % one new block adds (before the 1.1 chain factor); NAM: at Full
    val costLight: Float? = null,    // Melon NAM at Model Size Light
)

/** One block of the multi-FX chain (state.chain), in signal order. */
data class ChainBlock(
    val b: Int,                      // position in the chain (0-based)
    val plugin: Int,                 // index into plugins (-1 = unknown)
    val name: String,
    val uri: String,
    val cat: String,
    val tag: String,
    val on: Boolean,
    val cost: Float,                 // DSP %
)

/** DSP numbers in % of the JACK period (docs/dsp-budget.md). load/peak/xruns only with the live meter. */
data class Dsp(val predicted: Float, val limit: Float, val load: Float?, val peak: Float?, val xruns: Int?) {
    /** What fits: the pedal adds 1.1 x a block's cost to the chain's prediction. */
    fun fits(cost: Float): Boolean = maxOf(predicted, peak ?: 0f) + 1.1f * cost <= limit
    val shown: Float get() = load ?: predicted
}

/** One folder of a NAM / IR library, as sent by the pedal (ev "lib_list"). */
data class LibListing(
    val gen: Int,
    val index: Int,                       // control index
    val folder: String,                   // "" = top level
    val dirs: List<Pair<String, Int>>,    // sub-folder name, files inside (all levels)
    val files: List<String>,              // file names in this folder
    val current: String?,                 // chosen file (path inside the library)
    val total: Int,
)

object LibPath {
    /** "Marshall/JCM800/Crunch.nam" -> "Crunch" */
    fun title(path: String?): String {
        if (path.isNullOrEmpty()) return "None"
        val name = path.substringAfterLast('/')
        return if ('.' in name) name.substringBeforeLast('.') else name
    }

    /** "Marshall/JCM800/Crunch.nam" -> "Marshall/JCM800" */
    fun folder(path: String?): String = if (path != null && '/' in path) path.substringBeforeLast('/') else ""

    fun join(folder: String, name: String) = if (folder.isEmpty()) name else "$folder/$name"
}

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

/** Wi-Fi of the pedal (NetworkManager on the Pi), see melon_pedald/wifi.py. */
data class WifiStatus(
    val device: String?,          // "wlan0", or null when the Pi has no Wi-Fi adapter
    val connected: Boolean,
    val ssid: String?,
    val signal: Int?,             // 0-100
    val ip: String?,
    val hostname: String?,
    val user: String? = null,     // account on the pedal, for "ssh user@ip"
)

data class WifiNetwork(val ssid: String, val signal: Int, val secure: Boolean, val known: Boolean, val active: Boolean)

data class WifiResult(val ok: Boolean, val msg: String)

data class WifiState(
    val status: WifiStatus? = null,
    val saved: List<String> = emptyList(),
    val networks: List<WifiNetwork>? = null,   // null until the first scan
    val busy: String? = null,                  // "Scanning…", "Connecting to X…"
    val result: WifiResult? = null,
)

/** One input or output choice of the audio interface (ev "audio"): "In 1", "In 1+2", "Out 3+4"… */
data class IoOption(val id: String, val label: String, val stereo: Boolean)

/** Inputs / outputs of the interface the pedal runs on (melon_pedald/audio_io.py). */
data class AudioIo(
    val card: String,                 // "Sono", "AMS22", "sndrpihifiberry"…
    val info: String,                 // "USB-Audio - Audient Sono (12 in / 4 out)"
    val inputs: List<IoOption>,
    val outputs: List<IoOption>,
    val input: String,                // id of the input in use
    val output: String,               // id of the output in use
)

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
    val files: List<String?> = emptyList(),   // chosen file per control (library controls only)
    val listing: LibListing? = null,          // last folder listing asked for
    val chainSupported: Boolean = false,      // pedal speaks the multi-FX chain API (hello "features")
    val chain: List<ChainBlock> = emptyList(),
    val cur: Int = 0,                         // selected block: the one on the knobs and on the Sound tab
    val dsp: Dsp? = null,
    val synced: Boolean = false,          // got the first full state after connecting
    val error: String? = null,
    val wifi: WifiState = WifiState(),
    val audioSupported: Boolean = false,      // pedal can choose inputs / outputs (hello "features")
    val audio: AudioIo? = null,
) {
    fun slotLabel(slot: Int) = "${slot / bankSize + 1}-${"%02d".format(slot % bankSize + 1)}"

    val selectedBlock: ChainBlock? get() = chain.getOrNull(cur)
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
    fun libList(gen: Int, index: Int, folder: String) =
        op("lib_list").put("gen", gen).put("i", index).put("folder", folder).toString()
    fun setFile(gen: Int, index: Int, path: String?) =
        op("set_file").put("gen", gen).put("i", index).put("path", path ?: JSONObject.NULL).toString()

    // multi-FX chain (blocks are 0-based positions)
    fun addBlock(plugin: Int) = op("add_block").put("i", plugin).toString()
    fun removeBlock(b: Int) = op("remove_block").put("b", b).toString()
    fun moveBlock(b: Int, to: Int) = op("move_block").put("b", b).put("to", to).toString()
    fun blockOn(b: Int, on: Boolean) = op("block_on").put("b", b).put("on", on).toString()
    fun selectBlock(b: Int) = op("select_block").put("b", b).toString()

    fun getAudio() = op("get").put("what", "audio").toString()
    /** Use input [input] and/or output [output] (ids from AudioIo); null = leave as it is. */
    fun audioSet(input: String?, output: String?) = op("audio_set").apply {
        input?.let { put("in", it) }
        output?.let { put("out", it) }
    }.toString()

    fun wifiStatus() = op("wifi_status").toString()
    fun wifiScan() = op("wifi_scan").toString()
    fun wifiConnect(ssid: String, password: String?, hidden: Boolean) =
        op("wifi_connect").put("ssid", ssid).put("password", password ?: JSONObject.NULL).put("hidden", hidden).toString()
    fun wifiForget(ssid: String) = op("wifi_forget").put("ssid", ssid).toString()

    private fun optStr(o: JSONObject, key: String): String? = if (o.isNull(key)) null else o.optString(key)

    private fun applyWifi(w: WifiState, o: JSONObject): WifiState {
        var n = w
        o.optJSONObject("status")?.let { st ->
            n = n.copy(status = WifiStatus(
                device = optStr(st, "device"),
                connected = st.optBoolean("connected"),
                ssid = optStr(st, "ssid"),
                signal = if (st.isNull("signal")) null else st.optInt("signal"),
                ip = optStr(st, "ip"),
                hostname = optStr(st, "hostname"),
                user = optStr(st, "user"),
            ))
        }
        o.optJSONArray("saved")?.let { arr -> n = n.copy(saved = (0 until arr.length()).map { arr.optString(it) }) }
        o.optJSONArray("networks")?.let { arr ->
            n = n.copy(networks = (0 until arr.length()).map {
                val x = arr.getJSONObject(it)
                WifiNetwork(x.optString("ssid"), x.optInt("signal"), x.optBoolean("secure"), x.optBoolean("known"), x.optBoolean("active"))
            })
        }
        if (o.has("busy")) n = n.copy(busy = optStr(o, "busy"))
        if (o.has("result")) n = n.copy(result = o.optJSONObject("result")?.let { WifiResult(it.optBoolean("ok"), it.optString("msg")) })
        return n
    }

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
            lib = o.optString("lib", "").ifEmpty { null },
        )
    }

    private fun optFloat(o: JSONObject, key: String): Float? =
        if (!o.has(key) || o.isNull(key)) null else o.optDouble(key).toFloat()

    private fun parseChain(arr: JSONArray?): List<ChainBlock> =
        if (arr == null) emptyList() else (0 until arr.length()).map {
            val b = arr.getJSONObject(it)
            ChainBlock(
                b = b.optInt("b", it),
                plugin = if (b.isNull("i")) -1 else b.optInt("i", -1),
                name = b.optString("name"),
                uri = b.optString("uri"),
                cat = b.optString("cat"),
                tag = b.optString("tag").ifEmpty { b.optString("name").removePrefix("Melon ").take(5).uppercase() },
                on = b.optBoolean("on", true),
                cost = b.optDouble("cost", 0.0).toFloat(),
            )
        }

    private fun parseDsp(o: JSONObject?): Dsp? = o?.let {
        Dsp(
            predicted = it.optDouble("predicted", 0.0).toFloat(),
            limit = it.optDouble("limit", 85.0).toFloat(),
            load = optFloat(it, "load"),
            peak = optFloat(it, "peak"),
            xruns = if (it.has("xruns") && !it.isNull("xruns")) it.optInt("xruns") else null,
        )
    }

    private fun strings(arr: JSONArray?): List<String?> =
        if (arr == null) emptyList() else (0 until arr.length()).map { if (arr.isNull(it)) null else arr.optString(it) }

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
            "hello" -> {
                val f = o.optJSONArray("features")
                val has = { name: String -> f != null && (0 until f.length()).any { f.optString(it) == name } }
                s.copy(pedalName = o.optString("name", s.pedalName), chainSupported = has("chain"),
                       audioSupported = has("audio"))
            }
            "plugins" -> {
                val arr = o.optJSONArray("list") ?: JSONArray()
                s.copy(plugins = (0 until arr.length()).map {
                    val p = arr.getJSONObject(it)
                    PluginInfo(
                        p.optInt("i", it), p.optString("name"), p.optString("uri"), p.optInt("n"),
                        cat = p.optString("cat"), tag = p.optString("tag"),
                        cost = optFloat(p, "cost"), costLight = optFloat(p, "cost_light"),
                    )
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
                    files = controls.map { null },
                    listing = null,
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
                    files = if (o.has("files")) strings(o.optJSONArray("files")) else s.files,
                    chain = if (o.has("chain")) parseChain(o.optJSONArray("chain")) else s.chain,
                    cur = o.optInt("cur", s.cur),
                    dsp = if (o.has("dsp")) parseDsp(o.optJSONObject("dsp")) else s.dsp,
                    synced = true,
                )
            }
            "param" -> {
                val i = o.optInt("i", -1)
                if (s.plugin == null || o.optInt("gen") != s.plugin.gen || i !in s.values.indices || keepLocal(i)) s
                else s.copy(values = s.values.toMutableList().also { it[i] = o.optDouble("v").toFloat() })
            }
            "lib_list" -> {
                if (s.plugin == null || o.optInt("gen") != s.plugin.gen) return s
                val d = o.optJSONArray("dirs") ?: JSONArray()
                s.copy(
                    listing = LibListing(
                        gen = o.optInt("gen"),
                        index = o.optInt("i"),
                        folder = o.optString("folder", ""),
                        dirs = (0 until d.length()).map { d.getJSONArray(it).let { a -> a.getString(0) to a.optInt(1) } },
                        files = strings(o.optJSONArray("files")).filterNotNull(),
                        current = if (o.isNull("current")) null else o.optString("current"),
                        total = o.optInt("total"),
                    ),
                )
            }
            "audio" -> {
                fun opts(arr: JSONArray?) = if (arr == null) emptyList() else (0 until arr.length()).map {
                    val x = arr.getJSONObject(it)
                    IoOption(x.optString("id"), x.optString("label"), x.optBoolean("stereo"))
                }
                s.copy(audio = AudioIo(
                    card = o.optString("card"),
                    info = o.optString("info"),
                    inputs = opts(o.optJSONArray("inputs")),
                    outputs = opts(o.optJSONArray("outputs")),
                    input = o.optString("in"),
                    output = o.optString("out"),
                ))
            }
            "bypass" -> s.copy(bypass = o.optBoolean("on"))
            "wifi" -> s.copy(wifi = applyWifi(s.wifi, o))
            "error" -> s.copy(error = o.optString("msg"))
            else -> s
        }
    }
}
