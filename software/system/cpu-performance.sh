#!/bin/sh
# CPU at full speed while the pedal runs (no clock changes in the middle of the audio).
for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo performance > "$g" 2>/dev/null
done
exit 0
