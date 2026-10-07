// Aides de test : assert actif même en Release, comparaison numérique qui affiche les valeurs.
#pragma once

#undef NDEBUG
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdlib>

#define CHECK_NEAR(a, b, eps)                                                                    \
    do {                                                                                         \
        const double a_ = (a), b_ = (b);                                                         \
        if (!(std::fabs(a_ - b_) <= (eps))) {                                                    \
            std::fprintf(stderr, "%s:%d CHECK_NEAR %s = %.12g, attendu %s = %.12g\n", __FILE__, \
                         __LINE__, #a, a_, #b, b_);                                              \
            std::abort();                                                                        \
        }                                                                                        \
    } while (0)
