#include "borderDeco.hpp"

#include <algorithm>
#include <cmath>

#include <hyprland/src/Compositor.hpp>
#include <hyprland/src/animation/AnimationManager.hpp>
#include <hyprland/src/config/shared/animation/AnimationTree.hpp>
#include <hyprland/src/desktop/state/FocusState.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/render/Renderer.hpp>
#include <hyprutils/memory/Casts.hpp>
using namespace Hyprutils::Memory;
using namespace Render::GL;
#include "BorderppPassElement.hpp"
#include "globals.hpp"
#include "svgSlices.hpp"

using namespace BPPSvg;

static size_t borderCount() {
    return std::clamp<Config::INTEGER>(vars.addBorders->value(), 0, static_cast<Config::INTEGER>(vars.borderSizes.size()));
}

static float focusAlphaFor(PHLWINDOW pWindow) {
    return pWindow == Desktop::focusState()->window() ? 1.F : sc<float>(vars.inactiveAlpha->value());
}

CBordersPlusPlusSvg::CBordersPlusPlusSvg(PHLWINDOW pWindow) : IHyprWindowDecoration(pWindow), m_pWindow(pWindow) {
    m_lastWindowPos  = pWindow->position(Desktop::View::IGeometric::GEOMETRIC_CURRENT);
    m_lastWindowSize = pWindow->size(Desktop::View::IGeometric::GEOMETRIC_CURRENT);

    // dims unfocused windows' borders on the same animation as Hyprland's border colours
    Animation::mgr()->createAnimation(focusAlphaFor(pWindow), m_focusAlpha, Config::animationTree()->getAnimationPropertyConfig("border"), pWindow, AVARDAMAGE_NONE);
    m_focusAlpha->setUpdateCallback([this](auto) { damageEntire(); });
}

CBordersPlusPlusSvg::~CBordersPlusPlusSvg() {
    damageEntire();
}

SDecorationPositioningInfo CBordersPlusPlusSvg::getPositioningInfo() {
    SDecorationPositioningInfo info;
    info.policy   = DECORATION_POSITION_STICKY;
    info.reserved = true;
    info.priority = 9990;
    info.edges    = DECORATION_EDGE_BOTTOM | DECORATION_EDGE_LEFT | DECORATION_EDGE_RIGHT | DECORATION_EDGE_TOP;

    if (m_fLastThickness == 0) {
        double size = 0;

        for (size_t i = 0; i < borderCount(); ++i) {
            size += vars.borderSizes[i]->value();
        }

        info.desiredExtents = {{size, size}, {size, size}};
        m_fLastThickness    = size;
    } else
        info.desiredExtents = {{m_fLastThickness, m_fLastThickness}, {m_fLastThickness, m_fLastThickness}};

    return info;
}

void CBordersPlusPlusSvg::onPositioningReply(const SDecorationPositioningReply& reply) {
    m_bAssignedGeometry = reply.assignedGeometry;
}

uint64_t CBordersPlusPlusSvg::getDecorationFlags() {
    return DECORATION_PART_OF_MAIN_WINDOW;
}

eDecorationLayer CBordersPlusPlusSvg::getDecorationLayer() {
    return DECORATION_LAYER_OVER;
}

std::string CBordersPlusPlusSvg::getDisplayName() {
    return "Borders++ SVG";
}

void CBordersPlusPlusSvg::draw(PHLMONITOR pMonitor, const float& a) {
    if (!validMapped(m_pWindow))
        return;

    const auto PWINDOW = m_pWindow.lock();

    if (!PWINDOW->m_ruleApplicator->decorate().valueOrDefault())
        return;

    updateFocus(); // also picks up inactive_alpha changing on a reload

    CBorderPPSvgPassElement::SBorderPPData data;
    data.deco = this;
    data.a    = a; // the window's fade, so the borders fade in and out with it

    g_pHyprRenderer->m_renderPass.add(makeUnique<CBorderPPSvgPassElement>(data));
}

void CBordersPlusPlusSvg::drawPass(PHLMONITOR pMonitor, const float& a) {
    const auto  PWINDOW = m_pWindow.lock();

    static auto PROUNDING   = CConfigValue<Config::INTEGER>("decoration:rounding");
    static auto PBORDERSIZE = CConfigValue<Config::INTEGER>("general:border_size");

    const auto  BORDERS      = borderCount();
    const auto  NATURALROUND = vars.naturalRounding->value();
    const float ALPHA        = a * m_focusAlpha->value();

    if (BORDERS < 1)
        return;

    if (m_bAssignedGeometry.width < m_seExtents.topLeft.x + 1 || m_bAssignedGeometry.height < m_seExtents.topLeft.y + 1)
        return;

    const auto PWORKSPACE      = PWINDOW->m_workspace;
    const auto WORKSPACEOFFSET = PWORKSPACE && !PWINDOW->m_pinned ? PWORKSPACE->m_renderOffset->value() : Vector2D();

    auto       rounding      = PWINDOW->rounding() == 0 ? 0 : (PWINDOW->rounding() + *PBORDERSIZE) * pMonitor->m_scale;
    const auto ROUNDINGPOWER = PWINDOW->roundingPower();
    const auto ORIGINALROUND = rounding == 0 ? 0 : (PWINDOW->rounding() + *PBORDERSIZE) * pMonitor->m_scale;

    CBox       fullBox = m_bAssignedGeometry;
    fullBox.translate(g_pDecorationPositioner->getEdgeDefinedPoint(DECORATION_EDGE_BOTTOM | DECORATION_EDGE_LEFT | DECORATION_EDGE_RIGHT | DECORATION_EDGE_TOP, m_pWindow.lock()));

    fullBox.translate(PWINDOW->m_floatingOffset - pMonitor->m_position + WORKSPACEOFFSET);

    if (fullBox.width < 1 || fullBox.height < 1)
        return;

    double fullThickness = 0;

    for (size_t i = 0; i < BORDERS; ++i) {
        const int THISBORDERSIZE = vars.borderSizes[i]->value() == -1 ? *PBORDERSIZE : vars.borderSizes[i]->value();
        fullThickness += THISBORDERSIZE;
    }

    fullBox.expand(-fullThickness).scale(pMonitor->m_scale).round();

    for (size_t i = 0; i < BORDERS; ++i) {
        const int PREVBORDERSIZESCALED = i == 0 ? 0 : (vars.borderSizes[i - 1]->value() == -1 ? *PBORDERSIZE : vars.borderSizes[i - 1]->value()) * pMonitor->m_scale;
        const int THISBORDERSIZE       = vars.borderSizes[i]->value() == -1 ? *PBORDERSIZE : vars.borderSizes[i]->value();

        if (i != 0) {
            rounding += rounding == 0 ? 0 : PREVBORDERSIZESCALED;
            fullBox.x -= PREVBORDERSIZESCALED;
            fullBox.y -= PREVBORDERSIZESCALED;
            fullBox.width += PREVBORDERSIZESCALED * 2;
            fullBox.height += PREVBORDERSIZESCALED * 2;
        }

        if (fullBox.width < 1 || fullBox.height < 1)
            break;

        g_pHyprOpenGL->scissor(nullptr);

        // same truncation as PREVBORDERSIZESCALED so svg and color layers butt up against each other
        const int THISBORDERSIZESCALED = THISBORDERSIZE * pMonitor->m_scale;

        const int CORNERSCALED         = std::max(THISBORDERSIZE, cornerSize(i)) * pMonitor->m_scale;

        if (const auto* SLICES = getSlices(i, THISBORDERSIZESCALED, CORNERSCALED, sc<int>(std::lround(PWINDOW->rounding())))) {
            renderSlices(*SLICES, fullBox.copy().expand(THISBORDERSIZESCALED), THISBORDERSIZESCALED, CORNERSCALED, edgesRepeat(i), ALPHA);
            continue;
        }

        g_pHyprOpenGL->renderBorder(fullBox, CHyprColor{static_cast<uint64_t>(vars.borderColors[i]->value())},
                                    {.round         = NATURALROUND ? sc<int>(ORIGINALROUND) : sc<int>(rounding),
                                     .roundingPower = ROUNDINGPOWER,
                                     .borderSize    = THISBORDERSIZE,
                                     .a             = ALPHA,
                                     .outerRound    = NATURALROUND ? sc<int>(ORIGINALROUND) : -1});
    }

    m_seExtents = {{fullThickness, fullThickness}, {fullThickness, fullThickness}};

    m_bLastRelativeBox = CBox{0, 0, m_lastWindowSize.x, m_lastWindowSize.y}.addExtents(m_seExtents);

    if (fullThickness != m_fLastThickness) {
        m_fLastThickness = fullThickness;
        g_pDecorationPositioner->repositionDeco(this);
    }
}

eDecorationType CBordersPlusPlusSvg::getDecorationType() {
    return DECORATION_CUSTOM;
}

void CBordersPlusPlusSvg::updateWindow(PHLWINDOW pWindow) {
    m_lastWindowPos  = pWindow->position(Desktop::View::IGeometric::GEOMETRIC_CURRENT);
    m_lastWindowSize = pWindow->size(Desktop::View::IGeometric::GEOMETRIC_CURRENT);

    damageEntire();
}

void CBordersPlusPlusSvg::updateFocus() {
    if (const auto PWINDOW = m_pWindow.lock())
        *m_focusAlpha = focusAlphaFor(PWINDOW);
}

void CBordersPlusPlusSvg::damageEntire() {
    CBox dm = m_bLastRelativeBox.copy().translate(m_lastWindowPos).expand(2);
    g_pHyprRenderer->damageBox(dm);
}
