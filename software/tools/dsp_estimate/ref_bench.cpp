// x86 time of the plugins already measured on the Pi (docs/dsp-budget.md §2), same harness as mm_bench.
#include "ChorusDsp.h"
#include "FlangerDsp.h"
#include "DirtDsp.h"
#include "CompDsp.h"
#include "ReverbDsp.h"
#include "MuffsDsp.h"
#include "GateDsp.h"
#include "DelayDsp.h"
#include "ShifterDsp.h"
#include "MultiDelayDsp.h"
#include "SimpleGateDsp.h"
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
template <class E, class P> double bench() { double m = 1e9; for (int i = 0; i < 3; ++i) { E e; P p; e.setParams(p); e.prepare(FS, 2); e.setParams(p); m = std::min(m, run(e)); } return m; }
int main() {
#define B(name, ns, pi) std::printf("%-13s %8.4f %6.1f\n", name, bench<ns::Engine, ns::Params>(), pi);
    B("Chorus", chorus, 2.0) B("Flanger", flanger, 1.9) B("Dirt", dirt, 5.3) B("Comp", comp, 8.2)
    B("Reverberare", reverb, 15.7) B("Muffs", muffs, 25.8) B("GatesOfDoom", gate, 1.8) B("Delay2290", delay2290, 2.1)
    B("Shifter", shifter, 5.0) B("MultiDelay", mdelay, 2.4) B("SimpleGate", sgate, 0.9)
}
