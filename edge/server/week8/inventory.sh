#!/usr/bin/env bash
# Read-only inventory; missing tools are reported, not treated as readiness.
date -u +%FT%TZ
uname -a
cat /etc/os-release
python3 --version
for tool in lsusb bluetoothctl bluetoothd btmgmt btmon rfkill opkg gcc g++ pkg-config dbus-daemon; do
  command -v "$tool" || printf 'MISSING_TOOL=%s\n' "$tool"
done
command -v lsusb >/dev/null && lsusb
ls /sys/class/bluetooth 2>/dev/null || true
command -v bluetoothctl >/dev/null && bluetoothctl --version
command -v bluetoothctl >/dev/null && timeout 8 bluetoothctl list
command -v btmgmt >/dev/null && timeout 8 btmgmt info
command -v systemctl >/dev/null && systemctl --no-pager status dbus bluetooth 2>&1
for module in bluetooth btusb btrtl; do
  command -v modinfo >/dev/null && modinfo "$module" 2>&1
 done
if [ -r /proc/config.gz ]; then zcat /proc/config.gz | grep -E 'CONFIG_(BT|FW_LOADER|USB)'; fi
ls -l /lib/firmware/rtl_bt/*8761* 2>/dev/null || true
ls -ld /lib/modules/"$(uname -r)"/build 2>/dev/null || true
command -v opkg >/dev/null && opkg list-installed | grep -E 'bluez|dbus|python3|firmware|kernel-module-(btusb|btrtl|bluetooth)'
dmesg | tail -n 120
printf '\nINVENTORY_COLLECTED_REVIEW_REQUIRED (not BLE ready)\n'
