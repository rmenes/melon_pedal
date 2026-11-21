#!/bin/sh
# Waits for the audio interface (USB can appear a few seconds after boot), then starts JACK.
card="${JACK_DEVICE#hw:}"; card="${card%%,*}"
case "$card" in
    [0-9]*) path="/proc/asound/card$card" ;;
    *)      path="/proc/asound/$card" ;;
esac
i=0
while [ ! -e "$path" ]; do
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then
        echo "audio interface $JACK_DEVICE not found (check 'aplay -l')"
        exit 1
    fi
    sleep 1
done
exec jackd -R -P 80 -d alsa -d "$JACK_DEVICE" -r "$JACK_RATE" -p "$JACK_PERIOD" -n "$JACK_NPERIODS" $JACK_EXTRA
