#!/usr/bin/env bash
# Installs melon-display as a systemd service on the pedal (Raspberry Pi OS Lite, Trixie).
# Run from this folder:  sudo ./install.sh      Re-run it after every update.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo: sudo ./install.sh"; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
RUN_USER="${SUDO_USER:-pi}"
DEST=/opt/melon-display

echo "== packages"
apt-get install -y --no-install-recommends \
    python3-pil python3-numpy python3-spidev python3-gpiozero python3-lgpio fonts-dejavu-core curl

echo "== SPI"
if [ ! -e /dev/spidev0.0 ]; then
    raspi-config nonint do_spi 0
    NEED_REBOOT=1
fi
usermod -aG spi,gpio "$RUN_USER"

echo "== fonts (Fredoka + Barlow Semi Condensed, OFL)"
FONTS="$HERE/melon_display/fonts"
mkdir -p "$FONTS"
GF=https://raw.githubusercontent.com/google/fonts/main/ofl
get() { [ -s "$FONTS/$2" ] || curl -fsSL "$1" -o "$FONTS/$2" || { rm -f "$FONTS/$2"; echo "   could not download $2 (DejaVu will be used)"; }; }
get "$GF/fredoka/Fredoka%5Bwdth%2Cwght%5D.ttf" Fredoka-Variable.ttf
for w in Medium SemiBold Bold; do
    get "$GF/barlowsemicondensed/BarlowSemiCondensed-$w.ttf" "BarlowSemiCondensed-$w.ttf"
done

echo "== files -> $DEST"
mkdir -p "$DEST"
rm -rf "$DEST/melon_display"
cp -r "$HERE/melon_display" "$DEST/"
[ -f /etc/default/melon-display ] || cp "$HERE/melon-display.default" /etc/default/melon-display
sed "s/__USER__/$RUN_USER/" "$HERE/melon-display.service" > /etc/systemd/system/melon-display.service

echo "== service"
systemctl daemon-reload
systemctl enable melon-display.service
if [ "${NEED_REBOOT:-0}" = 1 ]; then
    echo; echo "SPI was just enabled: reboot now (sudo reboot). The display starts by itself afterwards."
else
    systemctl restart melon-display.service
    sleep 1
    systemctl --no-pager --lines=5 status melon-display.service || true
fi
