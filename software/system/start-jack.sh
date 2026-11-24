#!/bin/sh
# Starts JACK on the interface chosen by melon-audio (run as root by melon-jack.service just before this,
# see ExecStartPre): /run/melon-pedal/audio.env has the card, rate and buffer.
. /run/melon-pedal/audio.env
exec jackd -R -P 80 -d alsa -d "$JACK_DEVICE" -r "$JACK_RATE" -p "$JACK_PERIOD" -n "$JACK_NPERIODS" $JACK_EXTRA
