#pragma once
#include <algorithm>
#include <cmath>
#include <numeric>
#include <stdexcept>
#include <vector>
namespace nh {
// Complete linkage preserves pairwise cannot-links encoded by distance 2.
inline std::vector<size_t> complete_link(std::vector<float> distance, size_t n, float threshold) {
    if (n > 256 || distance.size() != n * n || !std::isfinite(threshold) || threshold <= 0 || threshold >= 2)
        throw std::invalid_argument("Invalid bounded clustering input");
    if (!std::all_of(distance.begin(), distance.end(), [](float d) { return std::isfinite(d) && d >= 0 && d <= 2; }))
        throw std::invalid_argument("Invalid cosine distance");
    std::vector<size_t> parent(n);
    std::iota(parent.begin(), parent.end(), 0);
    std::vector<bool> active(n, true);
    for (size_t step = 0; step < n; ++step) {
        float best = 2;
        size_t left = n, right = n;
        for (size_t i = 0; i < n; ++i)
            if (active[i])
                for (size_t j = i + 1; j < n; ++j)
                    if (active[j] && distance[i * n + j] < best) {
                        best = distance[i * n + j];
                        left = i;
                        right = j;
                    }
        if (left == n || best > threshold)
            break;
        active[right] = false;
        parent[right] = left;
        for (size_t k = 0; k < n; ++k)
            if (active[k] && k != left)
                distance[left * n + k] = distance[k * n + left] =
                    std::max(distance[left * n + k], distance[right * n + k]);
    }
    for (size_t i = 0; i < n; ++i) {
        size_t root = i;
        while (parent[root] != root)
            root = parent[root];
        parent[i] = root;
    }
    return parent;
}
} // namespace nh
