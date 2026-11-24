// x86 time of Melon Trem's DSP engine, same harness as ref_bench / mm_bench (docs/dsp-budget.md §9).
#include "TremDsp.h"
#include <chrono>
#include <cmath>
#include <cstdio>
#include <functional>
#include <random>
#include <vector>
static const int FS = 48000, BLOCK = 256, SECONDS = 20;
static std::vector<float> guitar() {
    std::vector<float> s((size_t) FS * 4); std::mt19937 rng(1); std::uniform_real_distribution<float> u(-1, 1);
    double f[] = { 82.4, 110, 146.8, 196, 246.9, 329.6 };
    for (size_t i = 0; i < s.size(); ++i) { double t = (double)(i % (FS / 2)) / FS; int n = (int)(i / (FS / 2)) % 6;
        s[i] = (float)(0.25 * std::exp(-4 * t) * (std::sin(2 * M_PI * f[n] * t) + 0.3 * std::sin(4 * M_PI * f[n] * t)) + 0.002 * u(rng)); }
    return s; }
template <class Eng> double run(Eng& e) {
    static auto sig = guitar(); std::vector<float> L(BLOCK), R(BLOCK); float* d[2] = { L.data(), R.data() };
    size_t pos = 0; const int blocks = SECONDS * FS / BLOCK;
    for (int b = 0; b < 200; ++b) { for (int i = 0; i < BLOCK; ++i) { L[i] = R[i] = sig[pos]; pos = (pos + 1) % sig.size(); } e.process(d, 2, BLOCK); }
    auto t0 = std::chrono::steady_clock::now();
    for (int b = 0; b < blocks; ++b) { for (int i = 0; i < BLOCK; ++i) { L[i] = R[i] = sig[pos]; pos = (pos + 1) % sig.size(); } e.process(d, 2, BLOCK); }
    double sec = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    volatile float sink = L[0] + R[1]; (void) sink; return sec / SECONDS * 100.0; }
static double bench(trem::Params p) { double m = 1e9; for (int i = 0; i < 3; ++i) { trem::Engine e; e.prepare(FS, 2); e.setParams(p); e.snapToTargets(); m = std::min(m, run(e)); } return m; }
int main() {
    auto show = [](const char* name, trem::Params p) { double x = bench(p); std::printf("%-22s x86 %7.4f %%  -> Pi est %4.1f %%\n", name, x, 0.2 + 4.45 * x); };
    trem::Params def;                                     show("Default (mono)", def);
    trem::Params sq; sq.wave = 1; sq.depth = 1; sq.rateHz = 12; show("Square 12 Hz (mono)", sq);
    trem::Params pan; pan.stereo = trem::pan; pan.wave = 0.2; pan.depth = 0.7; show("Pan", pan);
    trem::Params sqp = sq; sqp.stereo = trem::pan;        show("Square 12 Hz (pan)", sqp);
}
