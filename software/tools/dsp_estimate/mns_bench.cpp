// x86 time of Melon Monolithic Synthesis' DSP engine, same harness as ref_bench / trem_bench (docs/dsp-budget.md §10).
// Mono in (guitar), stereo out. One line per mode (sound 1, Params at 50 %).
#include "MonolithicEngine.h"
#include <chrono>
#include <cmath>
#include <cstdio>
#include <random>
#include <vector>
using namespace melon::mono;
static const int FS = 48000, BLOCK = 256, SECONDS = 20;
static std::vector<float> guitar() {
    std::vector<float> s((size_t) FS * 4); std::mt19937 rng(1); std::uniform_real_distribution<float> u(-1, 1);
    double f[] = { 82.4, 110, 146.8, 196, 246.9, 329.6 };
    for (size_t i = 0; i < s.size(); ++i) { double t = (double)(i % (FS / 2)) / FS; int n = (int)(i / (FS / 2)) % 6;
        s[i] = (float)(0.25 * std::exp(-4 * t) * (std::sin(2 * M_PI * f[n] * t) + 0.3 * std::sin(4 * M_PI * f[n] * t)) + 0.002 * u(rng)); }
    return s; }
static double run(MonolithicEngine& e) {
    static auto sig = guitar(); std::vector<float> in(BLOCK), L(BLOCK), R(BLOCK);
    size_t pos = 0; const int blocks = SECONDS * FS / BLOCK;
    auto blk = [&] { for (int i = 0; i < BLOCK; ++i) { in[i] = sig[pos]; pos = (pos + 1) % sig.size(); } e.process(in.data(), L.data(), R.data(), BLOCK); };
    for (int b = 0; b < 200; ++b) blk();
    auto t0 = std::chrono::steady_clock::now();
    for (int b = 0; b < blocks; ++b) blk();
    double sec = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    volatile float sink = L[0] + R[1]; (void) sink; return sec / SECONDS * 100.0; }
static double bench(EngineParams p) { double m = 1e9; for (int i = 0; i < 3; ++i) { MonolithicEngine e; e.prepare(FS); e.setParams(p); m = std::min(m, run(e)); } return m; }
int main(int argc, char** argv) {
    // Pi % = a + b * x86 %, fitted with ref_bench on the same computer (pass a b; default = 2026-11-23 desktop fit)
    double a = argc > 2 ? atof(argv[1]) : 0.02, b = argc > 2 ? atof(argv[2]) : 5.65;
    const char* names[] = { "LEAD", "PAD", "STRING", "BELL", "ORGAN", "BASS", "DUAL", "SWEEP", "NOISE", "SFX", "SEQ", "ARPEGGIO" };
    for (int m = 0; m < NumModes; ++m) { EngineParams p; p.mode = m; double x = bench(p);
        std::printf("%-10s x86 %7.4f %%  -> Pi est %4.1f %%\n", names[m], x, a + b * x); }
}
