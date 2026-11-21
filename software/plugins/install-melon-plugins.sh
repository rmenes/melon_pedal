#!/usr/bin/env bash
# Builds Melon Plugins (LV2, arm64) natively on the Pi and installs them to ~/.lv2,
# where melon-pedald finds them on its next start.
#
#   ./install-melon-plugins.sh                  # build + install the plugins that are missing
#   ./install-melon-plugins.sh --all            # rebuild + reinstall every plugin (e.g. after git pull)
#   ./install-melon-plugins.sh Shifter Tuner    # only these CMake targets
#   ./install-melon-plugins.sh --list           # show what is installed and what is missing
#   ./install-melon-plugins.sh --zip Melon-Plugins-v1.2.1-Linux-arm64.zip   # install from a release zip instead
#
# Env: MELON_PLUGINS_DIR (default ~/melon_plugins), JOBS (default 2), LV2_DEST (default ~/.lv2)
#
# Plugins in EXCLUDE are never built for the pedal, and their bundles are removed from LV2_DEST:
#   Rack - too heavy for the Pi 4 (amp/cab will come from simpler Melon Plugins later)
set -euo pipefail

SRC="${MELON_PLUGINS_DIR:-$HOME/melon_plugins}"
BUILD="$SRC/build-arm"
DEST="${LV2_DEST:-$HOME/.lv2}"
JOBS="${JOBS:-2}"
EXCLUDE="Rack"

die() { echo "error: $*" >&2; exit 1; }

# CMake target -> product name (= bundle name "Melon <name>.lv2"), read from the plugin's CMakeLists.txt
all_targets() { sed -n 's#^add_subdirectory(plugins/\(.*\))#\1#p' "$SRC/CMakeLists.txt"; }
excluded() { case " $EXCLUDE " in *" $1 "*) return 0;; esac; return 1; }
targets() { for t in $(all_targets); do excluded "$t" || echo "$t"; done; }
product() { sed -n 's/.*PRODUCT_NAME *"\(.*\)".*/\1/p' "$SRC/plugins/$1/CMakeLists.txt" | head -1; }
installed() { [ -f "$DEST/$(product "$1").lv2/manifest.ttl" ]; }

# Remove bundles of excluded plugins (left over from earlier installs), so melon-pedald doesn't load them
remove_excluded() {
    for t in $EXCLUDE; do
        local n b; n="$(product "$t" 2>/dev/null)"; [ -n "$n" ] || n="Melon $t"
        b="$DEST/$n.lv2"
        [ -d "$b" ] && { rm -rf "$b"; echo "removed $(basename "$b") (excluded from the pedal)"; }
    done
    return 0
}

install_zip() {
    local zip="$1" tmp; tmp="$(mktemp -d)"
    command -v unzip >/dev/null || sudo apt-get install -y unzip
    unzip -q "$zip" -d "$tmp"
    file "$tmp"/*/LV2/*.lv2/*.so | grep -q aarch64 || die "$zip has no arm64 binaries (use the Linux-arm64 zip)"
    mkdir -p "$DEST"; remove_excluded
    for b in "$tmp"/*/LV2/*.lv2; do
        n="$(basename "$b" .lv2)"
        for t in $EXCLUDE; do [ "$n" = "Melon $t" ] && { echo "skipped $n.lv2 (excluded from the pedal)"; continue 2; }; done
        rm -rf "$DEST/$(basename "$b")"; cp -r "$b" "$DEST/"; echo "installed $(basename "$b")"
    done
    rm -rf "$tmp"
}

[ "${1:-}" = "--zip" ] && { [ -n "${2:-}" ] || die "--zip needs a file"; install_zip "$2"; exit 0; }

[ -f "$SRC/CMakeLists.txt" ] || die "melon_plugins not found at $SRC (git clone it there or set MELON_PLUGINS_DIR)"

if [ "${1:-}" = "--list" ]; then
    for t in $(targets); do
        if installed "$t"; then s="installed"; else s="MISSING"; fi
        printf "%-12s %-24s %s\n" "$t" "$(product "$t")" "$s"
    done
    for t in $EXCLUDE; do [ -d "$SRC/plugins/$t" ] && printf "%-12s %-24s %s\n" "$t" "$(product "$t")" "excluded"; done
    exit 0
fi

mkdir -p "$DEST"; remove_excluded

# Which targets to build
if [ "${1:-}" = "--all" ]; then
    WANT=$(targets)
elif [ $# -gt 0 ]; then
    WANT="$*"
else
    WANT=""; for t in $(targets); do installed "$t" || WANT="$WANT $t"; done
fi
WANT=$(echo $WANT)
[ -n "$WANT" ] || { echo "All Melon Plugins are already installed in $DEST (use --all to rebuild)."; exit 0; }
for t in $WANT; do
    [ -d "$SRC/plugins/$t" ] || die "unknown plugin target: $t"
    excluded "$t" && die "$t is excluded from the pedal (see EXCLUDE at the top of this script)"
done
echo "Building: $WANT"

unset DISPLAY   # JUCE must not try to open an X connection
cmake -S "$SRC" -B "$BUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release -DMELON_FORMATS=LV2 \
      -DMELON_VST3_MANIFEST=OFF -DCMAKE_CXX_FLAGS="-mcpu=cortex-a72"

mkdir -p "$DEST"
FAILED=""
for t in $WANT; do
    j="$JOBS"
    echo; echo "=== $t (-j$j)"
    if cmake --build "$BUILD" --target "${t}_LV2" -j"$j"; then
        b="$BUILD/plugins/$t/${t}_artefacts/Release/LV2/$(product "$t").lv2"
        [ -d "$b" ] || { echo "bundle not found: $b"; FAILED="$FAILED $t"; continue; }
        rm -rf "$DEST/$(basename "$b")"; cp -r "$b" "$DEST/"
        echo "installed $(basename "$b") -> $DEST"
    else
        FAILED="$FAILED $t"
    fi
done

echo
[ -z "$FAILED" ] || echo "FAILED:$FAILED  (re-run with only those targets after fixing; JOBS=1 if the Pi ran out of memory)"
echo "Restart the controller to see the new plugins:  sudo systemctl restart melon-pedald"
