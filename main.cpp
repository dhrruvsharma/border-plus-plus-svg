#define WLR_USE_UNSTABLE

#include <unistd.h>

#include <any>
#include <array>
#include <hyprland/src/Compositor.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/desktop/state/FocusState.hpp>
#include <hyprland/src/config/ConfigManager.hpp>
#include <hyprland/src/render/Renderer.hpp>
#include <hyprland/src/event/EventBus.hpp>

#include "borderDeco.hpp"
#include "globals.hpp"
#include "svgSlices.hpp"

using namespace BPPSvg;

// Do NOT change this function.
APICALL EXPORT std::string PLUGIN_API_VERSION() {
    return HYPRLAND_API_VERSION;
}

static void onNewWindow(PHLWINDOW window) {
    if (std::ranges::any_of(window->m_windowDecorations, [](const auto& d) { return d->getDisplayName() == "Borders++ SVG"; }))
        return;

    HyprlandAPI::addWindowDecoration(PHANDLE, window, makeUnique<CBordersPlusPlusSvg>(window));
}

// start every border's fade as soon as focus moves, rather than whenever its window is next drawn
static void onFocusChange() {
    for (auto& w : Desktop::windowState()->windows()) {
        for (auto& d : w->m_windowDecorations) {
            if (d->getDisplayName() == "Borders++ SVG")
                static_cast<CBordersPlusPlusSvg*>(d.get())->updateFocus();
        }
    }
}

APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE handle) {
    PHANDLE = handle;

    const std::string HASH        = __hyprland_api_get_hash();
    const std::string CLIENT_HASH = __hyprland_api_get_client_hash();

    if (HASH != CLIENT_HASH) {
        HyprlandAPI::addNotification(PHANDLE, "[borders-plus-plus-svg] Failure in initialization: Version mismatch (headers ver is not equal to running hyprland ver)",
                                     CHyprColor{1.0, 0.2, 0.2, 1.0}, 5000);
        throw std::runtime_error("[bpp-svg] Version mismatch");
    }

    vars.addBorders =
        makeShared<Config::Values::CIntValue>("plugin:borders-plus-plus-svg:add_borders", "How many extra borders to draw", 1, Config::Values::SIntValueOptions{.min = 0, .max = 9});
    vars.naturalRounding = makeShared<Config::Values::CBoolValue>("plugin:borders-plus-plus-svg:natural_rounding", "Use the window's original rounding", true);
    vars.inactiveAlpha   = makeShared<Config::Values::CFloatValue>("plugin:borders-plus-plus-svg:inactive_alpha", "Opacity of the extra borders on windows without focus", 1.F,
                                                                 Config::Values::SFloatValueOptions{.min = 0.F, .max = 1.F});

    HyprlandAPI::addConfigValueV2(PHANDLE, vars.addBorders);
    HyprlandAPI::addConfigValueV2(PHANDLE, vars.naturalRounding);
    HyprlandAPI::addConfigValueV2(PHANDLE, vars.inactiveAlpha);

    static std::array<std::string, 9> borderColorNames;
    static std::array<std::string, 9> borderSizeNames;
    static std::array<std::string, 9> svgPathNames;
    static std::array<std::string, 9> svgSliceNames;
    static std::array<std::string, 9> svgEdgesNames;
    static std::array<std::string, 9> svgCornerNames;

    for (size_t i = 0; i < 9; ++i) {
        borderColorNames[i] = "plugin:borders-plus-plus-svg:col.border_" + std::to_string(i + 1);
        borderSizeNames[i]  = "plugin:borders-plus-plus-svg:border_size_" + std::to_string(i + 1);

        vars.borderColors[i] = makeShared<Config::Values::CColorValue>(borderColorNames[i].c_str(), "Color of the extra border", 0xee000000);
        vars.borderSizes[i]  = makeShared<Config::Values::CIntValue>(borderSizeNames[i].c_str(), "Size of the extra border", -1);

        HyprlandAPI::addConfigValueV2(PHANDLE, vars.borderColors[i]);
        HyprlandAPI::addConfigValueV2(PHANDLE, vars.borderSizes[i]);

        svgPathNames[i]  = "plugin:borders-plus-plus-svg:svg_" + std::to_string(i + 1);
        svgSliceNames[i] = "plugin:borders-plus-plus-svg:svg_slice_" + std::to_string(i + 1);
        svgEdgesNames[i] = "plugin:borders-plus-plus-svg:svg_edges_" + std::to_string(i + 1);

        vars.svgPaths[i]  = makeShared<Config::Values::CStringValue>(svgPathNames[i].c_str(), "SVG drawn as a 9-slice frame instead of the color, empty to disable", "");
        vars.svgSlices[i] = makeShared<Config::Values::CIntValue>(svgSliceNames[i].c_str(), "Size of the svg's corners in svg pixels, 0 for a third of its smaller side", 0,
                                                                  Config::Values::SIntValueOptions{.min = 0});
        vars.svgEdges[i]  = makeShared<Config::Values::CStringValue>(
            svgEdgesNames[i].c_str(), "How svg edges fill the border: stretch or repeat", "stretch",
            Config::Values::SStringValueOptions{.validator = [](const Config::STRING& v) -> std::expected<void, std::string> {
                if (v != "stretch" && v != "repeat")
                    return std::unexpected("must be stretch or repeat");
                return {};
            }});

        HyprlandAPI::addConfigValueV2(PHANDLE, vars.svgPaths[i]);
        HyprlandAPI::addConfigValueV2(PHANDLE, vars.svgSlices[i]);
        HyprlandAPI::addConfigValueV2(PHANDLE, vars.svgEdges[i]);

        svgCornerNames[i]  = "plugin:borders-plus-plus-svg:svg_corner_" + std::to_string(i + 1);
        vars.svgCorners[i] = makeShared<Config::Values::CIntValue>(svgCornerNames[i].c_str(), "Size of the svg's corners on screen, 0 for the border size. Bigger corners reach over the window's rounded corners", 0,
                                                                  Config::Values::SIntValueOptions{.min = 0});
        HyprlandAPI::addConfigValueV2(PHANDLE, vars.svgCorners[i]);
    }

    HyprlandAPI::reloadConfig();

    static auto P = Event::bus()->m_events.window.open.listen([&](PHLWINDOW w) { onNewWindow(w); });
    // re-read svg files on reload so edits show up without restarting
    static auto P2 = Event::bus()->m_events.config.reloaded.listen([] { clearSvgCache(); });
    static auto P3 = Event::bus()->m_events.window.active.listen([](PHLWINDOW, Desktop::eFocusReason) { onFocusChange(); });

    // add deco to existing windows
    for (auto& w : Desktop::windowState()->windows()) {
        if (w->isHidden() || !w->m_isMapped)
            continue;

        HyprlandAPI::addWindowDecoration(PHANDLE, w, makeUnique<CBordersPlusPlusSvg>(w));
    }

    HyprlandAPI::addNotification(PHANDLE, "[borders-plus-plus-svg] Initialized successfully!", CHyprColor{0.2, 1.0, 0.2, 1.0}, 5000);

    return {"borders-plus-plus-svg", "borders-plus-plus with 9-slice SVG borders.", "Vaxry, dhrruvsharma", "1.0"};
}

APICALL EXPORT void PLUGIN_EXIT() {
    g_pHyprRenderer->m_renderPass.removeAllOfType("CBorderPPSvgPassElement");
    clearSvgCache();
}
