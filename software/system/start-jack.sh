#!/bin/sh
# Chooses the audio interface (melon-audio select: JACK_DEVICE, or any USB interface when JACK_DEVICE=auto),
# waits for it (USB can appear a few seconds after boot), then starts JACK with its settings.
/usr/local/lib/melon-pedal/melon-audio select --wait 30 || exit 1
. /run/melon-pedal/audio.env
exec jackd -R -P 80 -d alsa -d "$JACK_DEVICE" -r "$JACK_RATE" -p "$JACK_PERIOD" -n "$JACK_NPERIODS" $JACK_EXTRA
