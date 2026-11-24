// Relative CPU cost of Melon MultiMod machines vs Melon Chorus / Flanger (same machine, same signal).
#include "MultiModDsp.h"
#include "ChorusDsp.h"
#include "FlangerDsp.h"
#include <chrono>
#include <cmath>
#include <cstdio>
#include <vector>
#include <random>

static const int FS = 48000, BLOCK = 256, SECONDS = 30;

static std::vector<float> guitar()
{   // plucked decaying tones with some noise, about -12 dBFS
    std::vector<float> s((size_t) FS * 4);
    std::mt19937 rng(1); std::uniform_real_distribution<float> u(-1, 1);
    double f[] = { 82.4, 110, 146.8, 196, 246.9, 329.6 };
    for (size_t i = 0; i < s.size(); ++i) {
        double t = (double)(i % (FS / 2)) / FS; int n = (int)(i / (FS / 2)) % 6;
        s[i] = (float)(0.25 * std::exp(-4 * t) * (std::sin(2 * M_PI * f[n] * t) + 0.3 * std::sin(4 * M_PI * f[n] * t)) + 0.002 * u(rng));
    }
    return s;
}

template <class Eng> double run(Eng& e)
{
    static auto sig = guitar();
    std::vector<float> L(BLOCK), R(BLOCK); float* d[2] = { L.data(), R.data() };
    size_t pos = 0; const int blocks = SECONDS * FS / BLOCK;
    for (int b = 0; b < 200; ++b) { for (int i = 0; i < BLOCK; ++i) { L[i] = R[i] = sig[pos]; pos = (pos + 1) % sig.size(); } e.process(d, 2, BLOCK); }
    auto t0 = std::chrono::steady_clock::now();
    for (int b = 0; b < blocks; ++b) {
        for (int i = 0; i < BLOCK; ++i) { L[i] = R[i] = sig[pos]; pos = (pos + 1) % sig.size(); }
        e.process(d, 2, BLOCK);
    }
    double sec = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    volatile float sink = L[0] + R[1]; (void) sink;
    return sec / SECONDS * 100.0;   // % of real time on this CPU
}

double best(std::function<double()> f) { double m = 1e9; for (int i = 0; i < 5; ++i) m = std::min(m, f()); return m; }

int main()
{
    double ch = best([] { chorus::Engine e; e.prepare(FS, 2); chorus::Params p; e.setParams(p); return run(e); });
    double fl = best([] { flanger::Engine e; e.prepare(FS, 2); flanger::Params p; e.setParams(p); return run(e); });
    std::printf("ref Chorus %.4f %%RT   Flanger %.4f %%RT\n", ch, fl);
    struct V { const char* name; int m; double p1, p2; };
    V vs[] = {
        {"Chorus (Classic)", mmod::chorus, 0.1, 0.5}, {"Chorus (Multi)", mmod::chorus, 0.9, 0.5},
        {"Flanger", mmod::flanger, 0.5, 0.5}, {"Rotary", mmod::rotary, 0.5, 0.5},
        {"Vibe", mmod::vibe, 0.5, 0.5}, {"Phaser (4 st)", mmod::phaser, 0.25, 0.5}, {"Phaser (16 st)", mmod::phaser, 0.99, 0.5},
        {"Filter", mmod::filter, 0.5, 0.1}, {"Formant", mmod::formant, 0.5, 0.5},
        {"Vintage Trem (Harmonic)", mmod::vintageTrem, 0.5, 0.5}, {"Pattern Trem", mmod::patternTrem, 0.5, 0.5},
        {"Autoswell", mmod::autoswell, 0.5, 0.5}, {"Destroyer", mmod::destroyer, 0.5, 0.5},
        {"Quadrature (AM)", mmod::quadrature, 0.1, 0.5}, {"Quadrature (FM)", mmod::quadrature, 0.35, 0.5},
        {"Quadrature (Shift Up)", mmod::quadrature, 0.6, 0.5},
    };
    for (auto& v : vs) {
        double c = best([&] { mmod::Engine e; mmod::Params p; p.machine = v.m; p.param1 = v.p1; p.param2 = v.p2;
                              e.setParams(p); e.prepare(FS, 2); e.setParams(p); return run(e); });
        std::printf("%-26s %.4f %%RT   x%.2f of Chorus   x%.2f of Flanger\n", v.name, c, c / ch, c / fl);
    }
}
