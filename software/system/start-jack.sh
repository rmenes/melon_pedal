#!/bin/sh
# Starts JACK on the interface chosen by melon-audio (run as root by melon-jack.service just before this,
# see ExecStartPre): /run/melon-pedal/audio.env has the card, rate and buffer.
. /run/melon-pedal/audio.env
if [ "$JACK_DEVICE" = dummy ]; then
    # no audio interface: silent JACK so mod-host, the controller and the Bluetooth app still run
    exec jackd -R -P 80 -d dummy -r "$JACK_RATE" -p "$JACK_PERIOD" -C 2 -P 2
fi
exec jackd -R -P 80 -d alsa -d "$JACK_DEVICE" -r "$JACK_RATE" -p "$JACK_PERIOD" -n "$JACK_NPERIODS" $JACK_EXTRA
