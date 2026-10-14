#include "svgSlices.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <format>
#include <memory>
#include <optional>
#include <unordered_map>
#include <vector>

#include <cairo/cairo.h>
#include <librsvg/rsvg.h>

#include <hyprland/src/render/OpenGL.hpp>
#include <hyprland/src/render/Renderer.hpp>

#include "globals.hpp"

using namespace Render::GL;

namespace BPPSvg {
    // an svg can hold one frame per window rounding, as top-level elements with these ids ("rounding-14")
    constexpr const char* VARIANT_ID  = "#rounding-";
    constexpr int         MAX_VARIANT = 200;

    struct SHandleDeleter {
        void operator()(RsvgHandle* handle) const {
            g_object_unref(handle);
        }
    };

    struct SLayerCache {
        std::string                                    path;
        int                                            slice  = 0;
        bool                                           failed = false;

        std::unique_ptr<RsvgHandle, SHandleDeleter>    handle; // parsed once per config reload
        double                                         w = 0, h = 0;
        std::vector<int>                               variants; // roundings the svg has a frame for, empty for a plain svg

        // by variant (-1 for a plain svg), then by thickness and corner size: one entry per monitor scale in practice
        std::unordered_map<int, std::unordered_map<uint64_t, SSvgSlices>> slices;
    };

    static std::array<SLayerCache, 9> g_cache;

    static std::string                expandPath(const std::string& path) {
        if (path.starts_with("~/")) {
            if (const char* HOME = getenv("HOME"))
                return std::string{HOME} + path.substr(1);
        }

        return path;
    }

    static std::string configuredPath(size_t layer) {
        auto path = vars.svgPaths[layer]->value();
        return path == "[[EMPTY]]" ? "" : path;
    }

    static std::string variantId(int rounding) {
        return std::format("{}{}", VARIANT_ID, rounding);
    }

    static bool load(SLayerCache& cache, std::string& err) {
        GError* gerr = nullptr;
        cache.handle.reset(rsvg_handle_new_from_file(expandPath(cache.path).c_str(), &gerr));

        if (!cache.handle) {
            err = gerr ? gerr->message : "failed to open file";
            g_clear_error(&gerr);
            return false;
        }

        if (!rsvg_handle_get_intrinsic_size_in_pixels(cache.handle.get(), &cache.w, &cache.h)) {
            // no absolute width/height, fall back to the viewBox
            gboolean      hasViewBox = false;
            RsvgRectangle viewBox    = {};
            rsvg_handle_get_intrinsic_dimensions(cache.handle.get(), nullptr, nullptr, nullptr, nullptr, &hasViewBox, &viewBox);

            if (!hasViewBox) {
                err = "the svg has neither a width/height nor a viewBox";
                return false;
            }

            cache.w = viewBox.width;
            cache.h = viewBox.height;
        }

        for (int r = 0; r <= MAX_VARIANT; ++r) {
            if (rsvg_handle_has_sub(cache.handle.get(), variantId(r).c_str()))
                cache.variants.push_back(r);
        }

        return true;
    }

    // the variant drawn around a window with this rounding: the closest one the svg has, -1 for a plain svg
    static int variantFor(const SLayerCache& cache, int rounding) {
        if (cache.variants.empty())
            return -1;

        return *std::ranges::min_element(cache.variants, {}, [rounding](int v) { return std::abs(v - rounding); });
    }

    static SP<Render::ITexture> cropToTexture(cairo_surface_t* src, int x, int y, int w, int h) {
        auto* piece = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, w, h);
        auto* cr    = cairo_create(piece);

        cairo_set_operator(cr, CAIRO_OPERATOR_SOURCE);
        cairo_set_source_surface(cr, src, -x, -y);
        cairo_paint(cr);
        cairo_destroy(cr);
        cairo_surface_flush(piece);

        auto tex = g_pHyprRenderer->createTexture(piece);
        cairo_surface_destroy(piece);
        return tex;
    }

    static std::optional<SSvgSlices> rasterize(const SLayerCache& cache, int variant, double slice, int t, int c, std::string& err) {
        if (slice <= 0)
            slice = std::min(cache.w, cache.h) / 3.0;

        if (slice * 2 >= cache.w || slice * 2 >= cache.h) {
            err = "svg_slice must be less than half of the svg's width and height";
            return std::nullopt;
        }

        // scale the whole svg so that one slice is exactly c pixels, keeping the corners crisp
        const double SCALE = c / slice;
        const int    W     = std::lround(cache.w * SCALE);
        const int    H     = std::lround(cache.h * SCALE);

        if (W - 2 * c < 1 || H - 2 * c < 1) {
            err = "svg_slice leaves no room for the edges";
            return std::nullopt;
        }

        auto*             surface  = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, W, H);
        auto*             cr       = cairo_create(surface);
        RsvgRectangle     viewport = {.x = 0, .y = 0, .width = sc<double>(W), .height = sc<double>(H)};
        GError*           gerr     = nullptr;

        const std::string ID = variant < 0 ? "" : variantId(variant);
        const bool        OK = rsvg_handle_render_layer(cache.handle.get(), cr, ID.empty() ? nullptr : ID.c_str(), &viewport, &gerr);

        cairo_destroy(cr);

        if (!OK) {
            err = gerr ? gerr->message : "failed to render svg";
            g_clear_error(&gerr);
            cairo_surface_destroy(surface);
            return std::nullopt;
        }

        cairo_surface_flush(surface);

        SSvgSlices result;
        // corners are c x c, edges are only the outer t pixels of the svg's edge band
        result.tex[SLICE_TOP_LEFT]     = cropToTexture(surface, 0, 0, c, c);
        result.tex[SLICE_TOP]          = cropToTexture(surface, c, 0, W - 2 * c, t);
        result.tex[SLICE_TOP_RIGHT]    = cropToTexture(surface, W - c, 0, c, c);
        result.tex[SLICE_RIGHT]        = cropToTexture(surface, W - t, c, t, H - 2 * c);
        result.tex[SLICE_BOTTOM_RIGHT] = cropToTexture(surface, W - c, H - c, c, c);
        result.tex[SLICE_BOTTOM]       = cropToTexture(surface, c, H - t, W - 2 * c, t);
        result.tex[SLICE_BOTTOM_LEFT]  = cropToTexture(surface, 0, H - c, c, c);
        result.tex[SLICE_LEFT]         = cropToTexture(surface, 0, c, t, H - 2 * c);

        cairo_surface_destroy(surface);

        if (std::ranges::any_of(result.tex, [](const auto& tex) { return !tex || tex->m_texID == 0; })) {
            err = "failed to upload textures";
            return std::nullopt;
        }

        return result;
    }

    const SSvgSlices* getSlices(size_t layer, int thicknessPx, int cornerPx, int rounding) {
        if (layer >= g_cache.size() || thicknessPx < 1)
            return nullptr;

        cornerPx = std::max(cornerPx, thicknessPx);

        const auto PATH  = configuredPath(layer);
        const auto SLICE = sc<int>(vars.svgSlices[layer]->value());
        auto&      cache = g_cache[layer];

        if (PATH.empty())
            return nullptr;

        if (cache.path != PATH || cache.slice != SLICE) {
            cache       = {};
            cache.path  = PATH;
            cache.slice = SLICE;
        }

        if (cache.failed)
            return nullptr;

        std::string err;
        auto        fail = [&] {
            cache.failed = true;
            HyprlandAPI::addNotification(PHANDLE, std::format("[borders-plus-plus-svg] svg_{}: {} ({})", layer + 1, err, PATH), CHyprColor{1.0, 0.2, 0.2, 1.0}, 7000);
            return nullptr;
        };

        if (!cache.handle && !load(cache, err))
            return fail();

        const int      VARIANT = variantFor(cache, rounding);
        auto&          bySize  = cache.slices[VARIANT];
        const uint64_t KEY     = (sc<uint64_t>(thicknessPx) << 32) | sc<uint32_t>(cornerPx);

        if (const auto IT = bySize.find(KEY); IT != bySize.end())
            return &IT->second;

        auto slices = rasterize(cache, VARIANT, SLICE, thicknessPx, cornerPx, err);
        if (!slices)
            return fail();

        return &bySize.emplace(KEY, std::move(*slices)).first->second;
    }

    // draws `tex` along one edge: stretched once, or as whole tiles scaled slightly so they fit exactly
    static void renderEdge(const SP<Render::ITexture>& tex, const CBox& box, bool horizontal, bool repeat, float a) {
        const double LENGTH = horizontal ? box.width : box.height;
        const double TILE   = horizontal ? tex->m_size.x : tex->m_size.y;

        if (LENGTH < 1)
            return;

        const int    COUNT = repeat && TILE >= 1 ? std::max<int>(1, std::lround(LENGTH / TILE)) : 1;
        const double START = horizontal ? box.x : box.y;

        for (int i = 0; i < COUNT; ++i) {
            // snap tile boundaries to whole pixels so neighbouring tiles don't leave seams
            const double FROM = std::round(START + LENGTH * i / COUNT);
            const double TO   = std::round(START + LENGTH * (i + 1) / COUNT);

            CBox         piece = horizontal ? CBox{FROM, box.y, TO - FROM, box.height} : CBox{box.x, FROM, box.width, TO - FROM};
            g_pHyprOpenGL->renderTexture(tex, piece, {.a = a});
        }
    }

    void renderSlices(const SSvgSlices& s, const CBox& o, int t, int c, bool repeatEdges, float a) {
        c = std::max(c, t);

        // corners bigger than the ring reach inwards, over the window's rounded-off corners
        const double RIGHT  = o.x + o.width;
        const double BOTTOM = o.y + o.height;
        const double C      = c;

        g_pHyprOpenGL->renderTexture(s.tex[SLICE_TOP_LEFT], CBox{o.x, o.y, C, C}, {.a = a});
        g_pHyprOpenGL->renderTexture(s.tex[SLICE_TOP_RIGHT], CBox{RIGHT - C, o.y, C, C}, {.a = a});
        g_pHyprOpenGL->renderTexture(s.tex[SLICE_BOTTOM_RIGHT], CBox{RIGHT - C, BOTTOM - C, C, C}, {.a = a});
        g_pHyprOpenGL->renderTexture(s.tex[SLICE_BOTTOM_LEFT], CBox{o.x, BOTTOM - C, C, C}, {.a = a});

        renderEdge(s.tex[SLICE_TOP], CBox{o.x + C, o.y, o.width - 2 * C, sc<double>(t)}, true, repeatEdges, a);
        renderEdge(s.tex[SLICE_BOTTOM], CBox{o.x + C, BOTTOM - t, o.width - 2 * C, sc<double>(t)}, true, repeatEdges, a);
        renderEdge(s.tex[SLICE_LEFT], CBox{o.x, o.y + C, sc<double>(t), o.height - 2 * C}, false, repeatEdges, a);
        renderEdge(s.tex[SLICE_RIGHT], CBox{RIGHT - t, o.y + C, sc<double>(t), o.height - 2 * C}, false, repeatEdges, a);
    }

    bool edgesRepeat(size_t layer) {
        return vars.svgEdges[layer]->value() == "repeat";
    }

    int cornerSize(size_t layer) {
        return vars.svgCorners[layer]->value();
    }

    void clearSvgCache() {
        g_cache = {};
    }
}
