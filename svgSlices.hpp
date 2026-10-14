#pragma once

#define WLR_USE_UNSTABLE

#include <array>

#include <hyprland/src/render/Texture.hpp>

namespace BPPSvg {
    // the 8 outer pieces of a 9-slice svg, the center is never drawn (the window covers it)
    enum eSlice : uint8_t {
        SLICE_TOP_LEFT = 0,
        SLICE_TOP,
        SLICE_TOP_RIGHT,
        SLICE_RIGHT,
        SLICE_BOTTOM_RIGHT,
        SLICE_BOTTOM,
        SLICE_BOTTOM_LEFT,
        SLICE_LEFT,
        SLICE_COUNT,
    };

    struct SSvgSlices {
        std::array<SP<Render::ITexture>, SLICE_COUNT> tex;
    };

    // returns the slices of border layer `layer` rasterized so the svg's corner slice is `cornerPx` (at least `thicknessPx`)
    // and its edges are `thicknessPx` thick, or nullptr if the layer has no svg (or it failed to load, in which case
    // the color border is used). An svg holding frames for several roundings ("rounding-N" elements) gives the one
    // closest to `rounding`, the window's rounding in logical pixels.
    const SSvgSlices* getSlices(size_t layer, int thicknessPx, int cornerPx, int rounding);

    // draws the slices around `outer`, which is the outer edge of a ring `thicknessPx` thick
    void renderSlices(const SSvgSlices& slices, const CBox& outer, int thicknessPx, int cornerPx, bool repeatEdges, float a);

    bool edgesRepeat(size_t layer);

    // corner size of layer `layer` in logical pixels, 0 means the border size
    int cornerSize(size_t layer);

    void clearSvgCache();
}
