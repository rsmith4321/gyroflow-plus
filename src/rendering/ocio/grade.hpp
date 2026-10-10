// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <OpenColorIO/OpenColorIO.h>
#include <array>
#include <cmath>
#include <stdexcept>
#include <vector>
namespace gp_ocio {
namespace OCIO = OCIO_NAMESPACE;
struct Settings {
    double brightness, contrast, shadows, highlights, exposure, saturation, warmth, tint;
};

inline OCIO::GroupTransformRcPtr definition(const Settings & s, bool bake_tone=false) {
    const std::array<double, 8> values = {s.brightness,s.contrast,s.shadows,s.highlights,
        s.exposure,s.saturation,s.warmth,s.tint};
    const std::array<double, 8> limits = {.5,.5,.5,.5,2,1,1,1};
    bool active = false;
    for (size_t i=0; i<values.size(); ++i) {
        if (!std::isfinite(values[i]) || std::abs(values[i]) > limits[i])
            throw std::invalid_argument("Adjustment outside the existing slider bounds");
        active = active || values[i] != 0;
    }
    auto group = OCIO::GroupTransform::Create();
    if (!active) return group;

    // Map the existing relative-balance/display-exposure slider semantics to
    // constant matrix parameters. OCIO evaluates all image operations. For
    // gamma-2.4 display RGB, decode -> linear gain -> encode is a multiplier.
    const std::array<double,3> stops = {.75*s.warmth+.25*s.tint,
        -.5*s.tint,-.75*s.warmth+.25*s.tint};
    const std::array<double,3> luma = {.2126,.7152,.0722};
    double norm = 0;
    for (size_t i=0;i<3;++i) norm += std::exp2(stops[i])*luma[i];
    double matrix[16] = {};
    for (size_t i=0;i<3;++i)
        matrix[i*5] = std::pow(std::exp2(stops[i]+s.exposure)/norm,1/2.4)*(1+s.contrast);
    matrix[15] = 1;
    const double offset[4] = {s.brightness-.5*s.contrast,
        s.brightness-.5*s.contrast,s.brightness-.5*s.contrast,0};
    auto affine = OCIO::MatrixTransform::Create();
    affine->setMatrix(matrix); affine->setOffset(offset); group->appendTransform(affine);

    auto clip = OCIO::RangeTransform::Create();
    clip->setMinInValue(0);clip->setMinOutValue(0);
    clip->setMaxInValue(1);clip->setMaxOutValue(1);
    group->appendTransform(clip);
    if (s.shadows || s.highlights) {
        OCIO::GradingTone value(OCIO::GRADING_VIDEO);
        value.m_shadows.m_master = 1+s.shadows;
        value.m_highlights.m_master = 1+s.highlights;
        auto tone = OCIO::GradingToneTransform::Create(OCIO::GRADING_VIDEO);
        tone->setValue(value);
        if (bake_tone) {
            // All tone inputs are bounded by the preceding OCIO Range op.
            // Generate with the official tone processor and let OCIO evaluate
            // the cached 1D LUT. No custom per-pixel curve/interpolation code.
            constexpr unsigned samples=4097;
            std::vector<float> ramp(samples*3);
            for (unsigned i=0;i<samples;++i) for (unsigned p=0;p<3;++p)
                ramp[i*3+p]=static_cast<float>(i)/static_cast<float>(samples-1);
            auto exact=OCIO::Config::CreateRaw()->getProcessor(tone)->getDefaultCPUProcessor();
            OCIO::PackedImageDesc image(ramp.data(),samples,1,3);exact->apply(image);
            auto lut=OCIO::Lut1DTransform::Create(samples,false);
            lut->setInterpolation(OCIO::INTERP_LINEAR);
            for (unsigned i=0;i<samples;++i)
                lut->setValue(i,ramp[i*3],ramp[i*3+1],ramp[i*3+2]);
            group->appendTransform(lut);
        } else group->appendTransform(tone);
    }
    if (s.saturation) {
        OCIO::GradingPrimary value(OCIO::GRADING_VIDEO);
        value.m_saturation = 1+s.saturation;
        auto primary = OCIO::GradingPrimaryTransform::Create(OCIO::GRADING_VIDEO);
        primary->setValue(value); group->appendTransform(primary);
    }
    group->appendTransform(clip);
    return group;
}

} // namespace gp_ocio
