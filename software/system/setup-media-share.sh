#!/usr/bin/env bash
# Melon Pedal — NAM / IR media folders + SMB share
#
# Creates:
#   /data/media/NAM   amp models (.nam)
#   /data/media/IR    cab impulse responses (.wav)
# and shares /data/media over SMB as  \\melon-pedal\Melon  (smb://melon-pedal.local/Melon)
#
# Run on the Pi:  sudo ./setup-media-share.sh [smb-user]
# smb-user defaults to the user who ran sudo. You'll be asked for an SMB password.
#
# Why everything lives under /data: the root filesystem is read-only in normal use
# (03-software-architecture.md §1/§8), so the media folders AND Samba's password
# database must sit on the writable /data partition or they vanish on reboot.

set -euo pipefail

MEDIA_ROOT=/data/media
SAMBA_STATE=/data/samba
GROUP=melon-media
SHARE=Melon
SMB_USER="${1:-${SUDO_USER:-}}"

[[ $EUID -eq 0 ]] || { echo "Run with sudo." >&2; exit 1; }
[[ -n "$SMB_USER" ]] || { echo "Usage: sudo $0 <smb-user>" >&2; exit 1; }
id "$SMB_USER" >/dev/null 2>&1 || { echo "User '$SMB_USER' does not exist." >&2; exit 1; }
mountpoint -q /data || echo "WARNING: /data is not a separate mount yet — continuing on the root FS."

echo "== Packages"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y samba wsdd avahi-daemon

echo "== Group and folders"
getent group "$GROUP" >/dev/null || groupadd --system "$GROUP"
usermod -aG "$GROUP" "$SMB_USER"
# The account that runs mod-host / melon-pedald must be able to read the files.
for svc_user in melon modhost; do
  id "$svc_user" >/dev/null 2>&1 && usermod -aG "$GROUP" "$svc_user" || true
done

install -d -o root -g "$GROUP" -m 2775 "$MEDIA_ROOT" "$MEDIA_ROOT/NAM" "$MEDIA_ROOT/IR"
install -d -m 0700 "$SAMBA_STATE" "$SAMBA_STATE/private" "$SAMBA_STATE/state" \
                   "$SAMBA_STATE/cache" "$SAMBA_STATE/lock"

cat > "$MEDIA_ROOT/README.txt" <<'EOF'
Melon Pedal media
  NAM/  Neural Amp Modeler files (.nam). Sub-folders are fine (e.g. NAM/Marshall/).
  IR/   Cabinet impulse responses (.wav, mono or stereo; 48 kHz preferred).
The pedal rescans these folders when files are added or removed.
EOF
chgrp "$GROUP" "$MEDIA_ROOT/README.txt"; chmod 0664 "$MEDIA_ROOT/README.txt"

echo "== Samba config"
[[ -f /etc/samba/smb.conf && ! -f /etc/samba/smb.conf.orig ]] && cp /etc/samba/smb.conf /etc/samba/smb.conf.orig
cat > /etc/samba/smb.conf <<EOF
# Managed by melon_pedal/software/system/setup-media-share.sh
[global]
   workgroup = WORKGROUP
   server string = Melon Pedal
   netbios name = MELON-PEDAL
   server role = standalone server
   security = user
   map to guest = never
   server min protocol = SMB2_10
   # Keep Samba's databases on the writable partition (read-only root)
   private dir = $SAMBA_STATE/private
   state directory = $SAMBA_STATE/state
   cache directory = $SAMBA_STATE/cache
   lock directory = $SAMBA_STATE/lock
   # Quiet and light: no printers, minimal logging (SD/USB wear, CPU)
   load printers = no
   printing = bsd
   printcap name = /dev/null
   disable spoolss = yes
   log level = 0
   logging = systemd
   # macOS compatibility
   vfs objects = fruit streams_xattr
   fruit:metadata = stream
   fruit:model = MacSamba

[$SHARE]
   comment = Melon Pedal NAM models and IRs
   path = $MEDIA_ROOT
   browseable = yes
   read only = no
   valid users = @$GROUP
   force group = $GROUP
   create mask = 0664
   directory mask = 2775
   veto files = /._*/.DS_Store/Thumbs.db/desktop.ini/
   delete veto files = yes
EOF
testparm -s >/dev/null

echo "== Keep Samba off the audio cores (audio runs on cores 2-3)"
for unit in smbd nmbd wsdd; do
  mkdir -p "/etc/systemd/system/$unit.service.d"
  cat > "/etc/systemd/system/$unit.service.d/melon-affinity.conf" <<'EOF'
[Service]
CPUAffinity=0 1
Nice=10
IOSchedulingClass=idle
EOF
done

echo "== Advertise the share (macOS Finder / Linux)"
cat > /etc/avahi/services/smb.service <<'EOF'
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">%h</name>
  <service><type>_smb._tcp</type><port>445</port></service>
</service-group>
EOF

systemctl daemon-reload
systemctl enable --now smbd wsdd avahi-daemon
systemctl disable --now nmbd 2>/dev/null || true   # NetBIOS not needed; wsdd handles Windows discovery
systemctl restart smbd avahi-daemon

echo "== SMB password for '$SMB_USER'"
smbpasswd -a "$SMB_USER"
smbpasswd -e "$SMB_USER"

IP=$(hostname -I | awk '{print $1}')
cat <<EOF

Done.
  Windows:  \\\\melon-pedal\\$SHARE   (or \\\\$IP\\$SHARE)
  macOS:    smb://melon-pedal.local/$SHARE
  Linux:    smb://melon-pedal.local/$SHARE
  Login:    $SMB_USER + the SMB password you just set
On the Pi: $MEDIA_ROOT/NAM and $MEDIA_ROOT/IR
EOF
