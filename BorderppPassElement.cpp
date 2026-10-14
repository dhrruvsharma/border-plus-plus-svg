#include "BorderppPassElement.hpp"
#include <hyprland/src/render/OpenGL.hpp>
#include <hyprland/src/render/Renderer.hpp>
#include "borderDeco.hpp"

CBorderPPSvgPassElement::CBorderPPSvgPassElement(const CBorderPPSvgPassElement::SBorderPPData& data_) : data(data_) {
    ;
}

std::vector<UP<IPassElement>> CBorderPPSvgPassElement::draw() {
    data.deco->drawPass(g_pHyprRenderer->m_renderData.pMonitor.lock(), data.a);
    return {};
}

bool CBorderPPSvgPassElement::needsLiveBlur() {
    return false;
}

bool CBorderPPSvgPassElement::needsPrecomputeBlur() {
    return false;
}
