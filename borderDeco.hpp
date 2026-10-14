#pragma once

#define WLR_USE_UNSTABLE

#include <hyprland/src/render/decorations/IHyprWindowDecoration.hpp>
#include <hyprland/src/helpers/AnimatedVariable.hpp>

class CBordersPlusPlusSvg : public IHyprWindowDecoration {
  public:
    CBordersPlusPlusSvg(PHLWINDOW);
    virtual ~CBordersPlusPlusSvg();

    virtual SDecorationPositioningInfo getPositioningInfo();

    virtual void                       onPositioningReply(const SDecorationPositioningReply& reply);

    virtual void                       draw(PHLMONITOR, float const& a);

    virtual eDecorationType            getDecorationType();

    virtual void                       updateWindow(PHLWINDOW);

    virtual void                       damageEntire();

    virtual uint64_t                   getDecorationFlags();

    virtual eDecorationLayer           getDecorationLayer();

    virtual std::string                getDisplayName();

    // fade towards full opacity or inactive_alpha, following the window's focus
    void                               updateFocus();

  private:
    void         drawPass(PHLMONITOR, float const& a);

    SBoxExtents  m_seExtents;

    PHLWINDOWREF m_pWindow;

    CBox         m_bLastRelativeBox;
    CBox         m_bAssignedGeometry;

    Vector2D     m_lastWindowPos;
    Vector2D     m_lastWindowSize;

    double       m_fLastThickness = 0;

    PHLANIMVAR<float> m_focusAlpha;

    friend class CBorderPPSvgPassElement;
};
