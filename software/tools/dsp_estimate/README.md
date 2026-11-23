# DSP cost estimate without the Pi

Times the plain DSP engines (`plugins/*/Source/*Dsp.h` in melon_plugins, no JUCE) on any computer, to estimate a
new plugin's cost on the pedal before benching it (docs/dsp-budget.md §8).

    P=~/melon_plugins/plugins
    g++ -std=c++17 -O2 $(for d in Chorus Flanger Dirt Comp Reverberare Muffs GatesOfDoom Delay2290 Shifter MultiDelay SimpleGate; do echo -n "-I$P/$d/Source "; done) -I$P/../shared ref_bench.cpp -o ref_bench && ./ref_bench
    g++ -std=c++17 -O2 -I$P/MultiMod/Source -I$P/Chorus/Source -I$P/Flanger/Source -I$P/../shared -include functional mm_bench.cpp -o mm_bench && ./mm_bench

`ref_bench` prints x86 % of real time next to the cost measured on the Pi; fit a line (Pi ≈ 0.2 + 4.45 × x86 on
2026-11-23, Muffs excluded) and apply it to the new plugin's numbers. Re-fit on another computer.
