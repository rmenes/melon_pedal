#!/usr/bin/env bash
# Installs the Bluetooth bridge as a service that starts with the pedal.
# Run from this folder:  sudo bash install.sh
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo: sudo bash install.sh"; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
RUN_USER="${SUDO_USER:-}"
[ -n "$RUN_USER" ] && [ "$RUN_USER" != root ] || { echo "Run with sudo from your normal user"; exit 1; }

if grep -qsE '^\s*dtoverlay=(disable-bt|pi3-disable-bt)' /boot/firmware/config.txt; then
    echo "Bluetooth is switched off in /boot/firmware/config.txt (dtoverlay=disable-bt). Remove that line and reboot."
    exit 1
fi

echo "== packages"
apt-get install -y --no-install-recommends bluez python3-dbus python3-gi
usermod -aG bluetooth "$RUN_USER"
rfkill unblock bluetooth || true
systemctl enable --now bluetooth.service

echo "== service (bridge in $HERE, user $RUN_USER)"
sed -e "s#__USER__#$RUN_USER#" -e "s#__BLE_DIR__#$HERE#" "$HERE/melon-ble.service" \
    > /etc/systemd/system/melon-ble.service
systemctl daemon-reload
systemctl enable melon-ble.service
systemctl restart melon-ble.service
sleep 3
systemctl --no-pager --lines=8 status melon-ble.service || true
echo
echo "Logs: journalctl -u melon-ble -f"
echo "If the log says 'Access denied' for org.bluez, change User=$RUN_USER to User=root in"
echo "/etc/systemd/system/melon-ble.service and run: sudo systemctl daemon-reload && sudo systemctl restart melon-ble"
