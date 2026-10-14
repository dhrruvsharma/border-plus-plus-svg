#pragma once

#include <array>

#include <hyprland/src/config/values/types/BoolValue.hpp>
#include <hyprland/src/config/values/types/ColorValue.hpp>
#include <hyprland/src/config/values/types/FloatValue.hpp>
#include <hyprland/src/config/values/types/IntValue.hpp>
#include <hyprland/src/config/values/types/StringValue.hpp>
#include <hyprland/src/plugins/PluginAPI.hpp>

// namespaced so this plugin can be loaded alongside the upstream borders-plus-plus
namespace BPPSvg {
    inline HANDLE PHANDLE = nullptr;

    struct SVars {
        SP<Config::Values::CIntValue>                   addBorders;
        SP<Config::Values::CBoolValue>                  naturalRounding;
        SP<Config::Values::CFloatValue>                 inactiveAlpha;
        std::array<SP<Config::Values::CColorValue>, 9>  borderColors;
        std::array<SP<Config::Values::CIntValue>, 9>    borderSizes;

        // 9-slice svg borders
        std::array<SP<Config::Values::CStringValue>, 9> svgPaths;
        std::array<SP<Config::Values::CIntValue>, 9>    svgSlices;
        std::array<SP<Config::Values::CStringValue>, 9> svgEdges;
        std::array<SP<Config::Values::CIntValue>, 9>    svgCorners;
    };

    inline SVars vars = {};
}
