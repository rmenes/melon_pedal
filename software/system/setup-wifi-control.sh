#!/usr/bin/env bash
# Melon Pedal — let the controller change Wi-Fi from the phone app
#
# melon-pedald runs as a normal user and changes Wi-Fi through NetworkManager (nmcli).
# NetworkManager only allows that for root or for users polkit approves, so this script:
#   - makes sure NetworkManager and polkit are installed
#   - adds the pedal user to the `netdev` group
#   - installs a polkit rule: members of `netdev` may manage NetworkManager without a password
#
# Run on the Pi:  sudo ./setup-wifi-control.sh [user]      (user defaults to the one who ran sudo)
# Then restart the controller so it picks up the new group:  sudo systemctl restart melon-pedald
#
# Read-only root (planned, 03-software-architecture §8): NetworkManager saves networks in
# /etc/NetworkManager/system-connections. Before the root becomes read-only, move them to
# /data (NetworkManager.conf [keyfile] path=...), or networks added from the app are lost on reboot.

set -euo pipefail

PEDAL_USER="${1:-${SUDO_USER:-}}"
RULE=/etc/polkit-1/rules.d/50-melon-networkmanager.rules

[[ $EUID -eq 0 ]] || { echo "Run with sudo." >&2; exit 1; }
[[ -n "$PEDAL_USER" ]] || { echo "Usage: sudo $0 <user>" >&2; exit 1; }
id "$PEDAL_USER" >/dev/null 2>&1 || { echo "User '$PEDAL_USER' does not exist." >&2; exit 1; }

echo "== Packages"
command -v nmcli >/dev/null && dpkg -s polkitd >/dev/null 2>&1 || {
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y network-manager polkitd
}
systemctl is-active --quiet NetworkManager || { echo "NetworkManager is not running: sudo systemctl enable --now NetworkManager" >&2; exit 1; }

echo "== Group"
getent group netdev >/dev/null || groupadd --system netdev
usermod -aG netdev "$PEDAL_USER"

echo "== polkit rule ($RULE)"
install -d -m 755 /etc/polkit-1/rules.d
cat > "$RULE" <<'RULES'
// Melon Pedal: the controller (group netdev) may scan, add, change and delete
// NetworkManager connections without a password, so the phone app can set up Wi-Fi.
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.NetworkManager.") == 0 && subject.isInGroup("netdev")) {
        return polkit.Result.YES;
    }
});
RULES
chmod 644 "$RULE"
systemctl restart polkit 2>/dev/null || true

echo "== Check"
if rfkill list wifi 2>/dev/null | grep -q "Soft blocked: yes"; then
  echo "WARNING: Wi-Fi is soft-blocked. Set the Wi-Fi country (sudo raspi-config → Localisation → WLAN Country) or run: sudo rfkill unblock wifi"
fi
# sudo -u reads the group list again, so the new netdev membership is already active here
echo "NetworkManager permissions for $PEDAL_USER (should say yes):"
sudo -u "$PEDAL_USER" nmcli -t -f PERMISSION,VALUE general permissions \
  | grep -E "settings.modify.system|network-control|wifi.scan" || true
echo "Done. Restart the controller:  sudo systemctl restart melon-pedald"
echo "Test from the Pi:  python3 ~/melon-ble/melon_remote_cli.py   then type:  {\"op\":\"wifi_status\"}"
