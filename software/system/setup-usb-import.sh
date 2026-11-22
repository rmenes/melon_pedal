#!/usr/bin/env bash
# Melon Pedal — automatic NAM / IR import from a USB stick
#
# On a Windows or Mac machine, make these folders at the top of a FAT32 or exFAT stick:
#     put_NAM_here/   .nam  .aidax  .json        (sub-folders are fine)
#     put_IR_here/    .wav  .aif  .aiff  .flac   (sub-folders are fine)
# Plug the stick into the pedal. It is mounted READ-ONLY, new or changed files are
# copied to /data/media/NAM and /data/media/IR, the stick is unmounted, and you
# can pull it out. Nothing on the stick is changed; nothing on the Pi is deleted.
#
# Install on the Pi:   sudo ./setup-usb-import.sh
# Watch an import:     journalctl -f -u 'melon-usb-import@*'
# Last result:         cat /run/melon-import/status.json

set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo." >&2; exit 1; }

MEDIA_ROOT=/data/media
GROUP=melon-media
OWNER_USER="${SUDO_USER:-}"

echo "== Folders"
getent group "$GROUP" >/dev/null || groupadd --system "$GROUP"
[[ -n "$OWNER_USER" ]] && usermod -aG "$GROUP" "$OWNER_USER"
install -d -o root -g "$GROUP" -m 2775 "$MEDIA_ROOT" "$MEDIA_ROOT/NAM" "$MEDIA_ROOT/IR"

echo "== Import script"
cat > /usr/local/sbin/melon-usb-import <<'SCRIPT'
#!/usr/bin/env bash
# Called by melon-usb-import@<dev>.service, e.g. "melon-usb-import sda1"
set -uo pipefail

DEV="$1"
NODE="/dev/$DEV"
DEST=/data/media
GROUP=melon-media
RUN=/run/melon-import
MNT="$RUN/mnt-$DEV"
STATUS="$RUN/status.json"
NAM_EXT="nam aidax json"
IR_EXT="wav aif aiff flac"

mkdir -p "$RUN"
log() { echo "$*"; }
status() {  # state message nam ir
  local m=${2//\"/\'}
  printf '{"state":"%s","message":"%s","nam":%d,"ir":%d,"device":"%s","time":"%s"}\n' \
    "$1" "$m" "$3" "$4" "$DEV" "$(date -Is)" > "$STATUS.tmp" && mv -f "$STATUS.tmp" "$STATUS"
}

skip() { log "skip $NODE: $*"; exit 0; }

[[ -b "$NODE" ]] || skip "not a block device"

# --- Never touch the boot/OS stick -----------------------------------------
# Checks use the PHYSICAL disk, not PARTUUIDs: a stick once flashed with the same
# Pi OS image keeps the same MBR disk ID even after reformatting.
# 1) this partition is already mounted somewhere (e.g. /boot/firmware, /)
findmnt -rn -S "$NODE" >/dev/null && skip "already mounted"
# 2) same physical disk as anything currently mounted from /dev (the boot stick)
my_disk=$(lsblk -no PKNAME "$NODE" 2>/dev/null | head -n1)
[[ -z "$my_disk" ]] && my_disk="$DEV"          # stick formatted without a partition table
for src in $(findmnt -rn -o SOURCE | grep '^/dev/' | sed 's/\[.*//' | sort -u); do
  d=$(lsblk -no PKNAME "$src" 2>/dev/null | head -n1); [[ -z "$d" ]] && d=${src#/dev/}
  [[ "$d" == "$my_disk" ]] && skip "on the same disk as mounted $src (boot/OS disk)"
done
# 3) warn about a duplicated disk ID (can make the Pi mount the wrong /boot/firmware)
root_pu=$(grep -o 'root=PARTUUID=[^ ]*' /proc/cmdline | cut -d= -f3 || true)
my_pu=$(blkid -o value -s PARTUUID "$NODE" 2>/dev/null || true)
if [[ -n "$root_pu" && -n "$my_pu" && "${my_pu%-*}" == "${root_pu%-*}" ]]; then
  log "WARNING: /dev/$my_disk has the same disk ID as the boot stick (${root_pu%-*})." \
      "Change it: sudo sfdisk --disk-id /dev/$my_disk 0x<8 hex digits>"
fi

FSTYPE=$(blkid -o value -s TYPE "$NODE" 2>/dev/null || true)
case "$FSTYPE" in vfat|exfat) ;; *) skip "file system '$FSTYPE' (use FAT32 or exFAT)" ;; esac

# --- Mount read-only ---------------------------------------------------------
cleanup() {
  sync
  mountpoint -q "$MNT" && { umount "$MNT" 2>/dev/null || umount -l "$MNT"; }
  rmdir "$MNT" 2>/dev/null || true
}
trap cleanup EXIT
trap 'status error "Stick removed during import - plug it in again" 0 0; exit 1' TERM INT

mkdir -p "$MNT"
if ! mount -t "$FSTYPE" -o ro,nosuid,nodev,noexec "$NODE" "$MNT"; then
  log "Could not mount $NODE ($FSTYPE)"; exit 0
fi

find_dir() { find "$MNT" -mindepth 1 -maxdepth 1 -type d -iname "$1" -print -quit; }
SRC_NAM=$(find_dir put_NAM_here)
SRC_IR=$(find_dir put_IR_here)
if [[ -z "$SRC_NAM" && -z "$SRC_IR" ]]; then
  log "$NODE has no put_NAM_here / put_IR_here folder - ignored"; exit 0
fi

status importing "Importing from USB stick - don't remove it" 0 0
FAILED=0

import_dir() {  # src  dest-subfolder  "ext list"  -> prints number of files copied
  local src="$1" sub="$2" exts=" $3 " n=0 f rel base ext dst dir tmp
  [[ -n "$src" ]] || { echo 0; return; }
  while IFS= read -r -d '' f; do
    rel=${f#"$src"/}; base=${f##*/}
    [[ "$base" == .* ]] && continue                    # ._macOS, hidden files
    [[ "$rel" == */.* ]] && continue                   # files inside hidden folders
    ext=${base##*.}; ext=${ext,,}
    [[ "$exts" == *" $ext "* ]] || continue
    dst="$DEST/$sub/$rel"; dir=${dst%/*}
    [[ -f "$dst" ]] && cmp -s "$f" "$dst" && continue  # already there, identical
    install -d -g "$GROUP" -m 2775 "$dir" || { FAILED=1; continue; }
    tmp="$dir/.importing-$base"                        # hidden until complete
    if cp "$f" "$tmp" && chgrp "$GROUP" "$tmp" && chmod 0664 "$tmp" && mv -f "$tmp" "$dst"; then
      n=$((n + 1)); log "copied $sub/$rel" >&2
    else
      rm -f "$tmp"; FAILED=1; log "FAILED $sub/$rel" >&2
    fi
  done < <(find "$src" -type f -print0)
  echo "$n"
  return $FAILED
}

N_NAM=$(import_dir "$SRC_NAM" NAM "$NAM_EXT") || FAILED=1
N_IR=$(import_dir "$SRC_IR" IR "$IR_EXT") || FAILED=1
sync

if [[ $FAILED -eq 0 ]]; then
  status done "Imported $N_NAM NAM and $N_IR IR files - you can remove the stick" "$N_NAM" "$N_IR"
  log "Done: $N_NAM NAM, $N_IR IR"
else
  status error "Some files could not be copied (disk full?) - check the log" "$N_NAM" "$N_IR"
  log "Finished with errors: $N_NAM NAM, $N_IR IR copied"
fi
SCRIPT
chmod 0755 /usr/local/sbin/melon-usb-import

echo "== systemd unit"
cat > /etc/systemd/system/melon-usb-import@.service <<'UNIT'
[Unit]
Description=Melon Pedal: import NAM/IR files from USB stick %I
BindsTo=dev-%i.device
After=dev-%i.device local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/melon-usb-import %I
TimeoutStartSec=15min
# keep the copy away from the audio cores (2-3)
CPUAffinity=0 1
Nice=10
IOSchedulingClass=idle
UNIT

echo "== udev rule"
cat > /etc/udev/rules.d/99-melon-usb-import.rules <<'RULE'
# FAT32 / exFAT on a USB stick -> melon-usb-import@<dev>.service
ACTION=="add", SUBSYSTEM=="block", ENV{ID_BUS}=="usb", ENV{ID_FS_TYPE}=="vfat|exfat", TAG+="systemd", ENV{SYSTEMD_WANTS}+="melon-usb-import@%k.service"
RULE

systemctl daemon-reload
udevadm control --reload-rules

cat <<EOF

Done. Plug in a stick with put_NAM_here / put_IR_here folders.
  Follow it:    journalctl -f -u 'melon-usb-import@*'
  Last result:  cat /run/melon-import/status.json
  Files land in $MEDIA_ROOT/NAM and $MEDIA_ROOT/IR
EOF
