#pragma once
#include <hyprland/src/render/pass/PassElement.hpp>

class CBordersPlusPlusSvg;

class CBorderPPSvgPassElement : public IPassElement {
  public:
    struct SBorderPPData {
        CBordersPlusPlusSvg* deco = nullptr;
        float             a    = 1.F;
    };

    CBorderPPSvgPassElement(const SBorderPPData& data_);
    virtual ~CBorderPPSvgPassElement() = default;

    virtual std::vector<UP<IPassElement>> draw() override;
    virtual bool                          needsLiveBlur() override;
    virtual bool                          needsPrecomputeBlur() override;

    virtual const char*                   passName() override {
        return "CBorderPPSvgPassElement";
    }

    virtual ePassElementType type() override {
        return EK_CUSTOM;
    }

  private:
    SBorderPPData data;
};
