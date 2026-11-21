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
# Env: MELON_PLUGINS_DIR (default ~/melon_plugins), JOBS (default 2; Rack uses 1), LV2_DEST (default ~/.lv2)
set -euo pipefail

SRC="${MELON_PLUGINS_DIR:-$HOME/melon_plugins}"
BUILD="$SRC/build-arm"
DEST="${LV2_DEST:-$HOME/.lv2}"
JOBS="${JOBS:-2}"

die() { echo "error: $*" >&2; exit 1; }

# CMake target -> product name (= bundle name "Melon <name>.lv2"), read from the plugin's CMakeLists.txt
targets() { sed -n 's#^add_subdirectory(plugins/\(.*\))#\1#p' "$SRC/CMakeLists.txt"; }
product() { sed -n 's/.*PRODUCT_NAME *"\(.*\)".*/\1/p' "$SRC/plugins/$1/CMakeLists.txt" | head -1; }
installed() { [ -f "$DEST/$(product "$1").lv2/manifest.ttl" ]; }

install_zip() {
    local zip="$1" tmp; tmp="$(mktemp -d)"
    command -v unzip >/dev/null || sudo apt-get install -y unzip
    unzip -q "$zip" -d "$tmp"
    file "$tmp"/*/LV2/*.lv2/*.so | grep -q aarch64 || die "$zip has no arm64 binaries (use the Linux-arm64 zip)"
    mkdir -p "$DEST"
    for b in "$tmp"/*/LV2/*.lv2; do rm -rf "$DEST/$(basename "$b")"; cp -r "$b" "$DEST/"; echo "installed $(basename "$b")"; done
    rm -rf "$tmp"
}

[ "${1:-}" = "--zip" ] && { [ -n "${2:-}" ] || die "--zip needs a file"; install_zip "$2"; exit 0; }

[ -f "$SRC/CMakeLists.txt" ] || die "melon_plugins not found at $SRC (git clone it there or set MELON_PLUGINS_DIR)"

if [ "${1:-}" = "--list" ]; then
    for t in $(targets); do
        if installed "$t"; then s="installed"; else s="MISSING"; fi
        printf "%-12s %-24s %s\n" "$t" "$(product "$t")" "$s"
    done
    exit 0
fi

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
for t in $WANT; do [ -d "$SRC/plugins/$t" ] || die "unknown plugin target: $t"; done
echo "Building: $WANT"

unset DISPLAY   # JUCE must not try to open an X connection
cmake -S "$SRC" -B "$BUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release -DMELON_FORMATS=LV2 \
      -DMELON_VST3_MANIFEST=OFF -DCMAKE_CXX_FLAGS="-mcpu=cortex-a72" \
      -DMELON_RACK_TONE3000=OFF   # no libcurl on the pedal (Pi OS libssl-dev conflict); TONE3000 needs the desktop GUI anyway

mkdir -p "$DEST"
FAILED=""
for t in $WANT; do
    j="$JOBS"; [ "$t" = "Rack" ] && j=1   # NeuralAudio + LTO needs a lot of RAM on a 4 GB Pi
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
