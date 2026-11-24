#!/usr/bin/env bash
# Starts the Melon Pedal at boot: JACK -> mod-host -> controller (+ the display service).
# Run from this folder:  sudo bash install.sh      Re-run after changing these files.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo: sudo bash install.sh"; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
RUN_USER="${SUDO_USER:-}"
[ -n "$RUN_USER" ] && [ "$RUN_USER" != root ] || { echo "Run with sudo from your normal user"; exit 1; }
USER_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
PEDALD_DIR="${PEDALD_DIR:-$USER_HOME/melon-pedald}"

MODHOST="$(command -v mod-host || true)"
[ -n "$MODHOST" ] || { echo "mod-host not found in PATH"; exit 1; }
command -v jackd >/dev/null || { echo "jackd not found (sudo apt install jackd2)"; exit 1; }
[ -d "$PEDALD_DIR/melon_pedald" ] || { echo "controller not found in $PEDALD_DIR (set PEDALD_DIR=...)"; exit 1; }
systemctl list-unit-files melon-display.service >/dev/null 2>&1 || \
    echo "note: melon-display is not installed; the pedal works without the screen"

echo "== user $RUN_USER · controller $PEDALD_DIR · mod-host $MODHOST"
usermod -aG audio "$RUN_USER"

install -d /usr/local/lib/melon-pedal
install -m 755 "$HERE/start-jack.sh" "$HERE/cpu-performance.sh" /usr/local/lib/melon-pedal/
install -m 755 "$HERE/melon-audio.py" /usr/local/lib/melon-pedal/melon-audio
install -d /etc/melon-pedal/audio.d
for f in "$HERE"/audio.d/*.conf; do
    [ -e "/etc/melon-pedal/audio.d/$(basename "$f")" ] || cp "$f" /etc/melon-pedal/audio.d/
done
install -m 644 "$HERE/90-melon-audio.rules" /etc/udev/rules.d/
udevadm control --reload
[ -f /etc/default/melon-pedal ] || cp "$HERE/melon-pedal.default" /etc/default/melon-pedal

for u in melon-jack melon-modhost melon-pedald; do
    sed -e "s#__USER__#$RUN_USER#" -e "s#__MODHOST__#$MODHOST#" -e "s#__PEDALD_DIR__#$PEDALD_DIR#" \
        "$HERE/$u.service" > "/etc/systemd/system/$u.service"
done
cp "$HERE/melon-pedal.target" /etc/systemd/system/

if pgrep -x jackd >/dev/null || pgrep -x mod-host >/dev/null || pgrep -f "python3 -m melon_pedald" >/dev/null; then
    echo
    echo "jackd / mod-host / melon_pedald are still running by hand. Stop them first:"
    echo "   pkill -f 'python3 -m melon_pedald'; pkill mod-host; pkill jackd"
    echo "then run this installer again."
    systemctl daemon-reload
    exit 1
fi

systemctl daemon-reload
systemctl enable melon-pedal.target melon-jack.service melon-modhost.service melon-pedald.service
systemctl restart melon-pedal.target
sleep 6
systemctl --no-pager --lines=0 status melon-jack melon-modhost melon-pedald | grep -E "●|Active:" || true
echo
echo "Logs: journalctl -u melon-pedald -f     Stop: sudo systemctl stop melon-pedal.target"
