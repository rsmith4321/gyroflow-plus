// SPDX-License-Identifier: GPL-3.0-or-later
#include "bridge.h"
#include "grade.hpp"
#include <algorithm>
#include <cstring>
#include <limits>
#include <memory>
#include <mutex>
#include <string>

namespace {
namespace OCIO = OCIO_NAMESPACE;
static_assert(OCIO_VERSION_HEX == ((2<<24)|(4<<16)|(2<<8)), "Use pinned OpenColorIO 2.4.2 headers");

struct Prepared {
    OCIO::ConstProcessorRcPtr exact;
    OCIO::ConstCPUProcessorRcPtr cpu;
    mutable std::once_flag gpu_once;
    mutable OCIO::GpuShaderDescRcPtr gpu;
    OCIO::ConstGpuShaderDescRcPtr shader() const {
        std::call_once(gpu_once,[this] {
            auto candidate=OCIO::GpuShaderDesc::CreateShaderDesc();
            candidate->setLanguage(OCIO::GPU_LANGUAGE_GLSL_4_0);
            candidate->setFunctionName("applyOcioGrade");candidate->setResourcePrefix("gp_ocio_");
            candidate->setAllowTexture1D(false);
            // Qt's ShaderEffect sampler clamps U/V but defaults W to Repeat.
            // OCIO's range-combination optimization assumes every LUT sampler
            // clamps, and may remove our explicit input-domain Range op. Keep
            // that official operation in generated GPU code; no color algorithm
            // is rewritten here. CPU optimization remains unchanged.
            const auto flags=static_cast<OCIO::OptimizationFlags>(
                OCIO::OPTIMIZATION_DEFAULT & ~OCIO::OPTIMIZATION_COMP_RANGE);
            exact->getOptimizedGPUProcessor(flags)->extractGpuShaderInfo(candidate);
            if (candidate->getNumTextures() || candidate->getNum3DTextures()>1 || candidate->getNumUniforms())
                throw std::runtime_error("Unsupported OpenColorIO preview resources");
            if (candidate->getNum3DTextures()) {
                const char * texture,* sampler;unsigned edge;OCIO::Interpolation interpolation;
                candidate->get3DTexture(0,texture,sampler,edge,interpolation);
                if (edge<2 || edge>128 || interpolation!=OCIO::INTERP_NEAREST)
                    throw std::runtime_error("Unsupported OpenColorIO 3D texture layout");
            }
            gpu=candidate;
        });
        return gpu;
    }
    explicit Prepared(const double * p, const char * lut_path) {
        if (OCIO::GetVersionHex()!=OCIO_VERSION_HEX)
            throw std::runtime_error("OpenColorIO runtime does not match pinned 2.4.2 headers");
        gp_ocio::Settings s{p[0],p[1],p[2],p[3],p[4],p[5],p[6],p[7]};
        // A fresh config per immutable snapshot prevents stale same-size sampled
        // Lut1D processor cache keys when grading parameters change.
        auto config=OCIO::Config::CreateRaw();
        auto definition=[&](bool bake_tone) {
            auto group=OCIO::GroupTransform::Create();
            if (lut_path && *lut_path) {
                // Canonical .cube input domain is 0..1, matching FFmpeg's LUT
                // input clamp. Also keeps native Qt 3D texture sampling inside
                // its domain (QSGTexture exposes only U/V sampler wrap modes).
                auto domain=OCIO::RangeTransform::Create();
                domain->setMinInValue(0);domain->setMinOutValue(0);
                domain->setMaxInValue(1);domain->setMaxOutValue(1);
                group->appendTransform(domain);
                auto lut=OCIO::FileTransform::Create();
                lut->setSrc(lut_path);lut->setInterpolation(OCIO::INTERP_TETRAHEDRAL);
                group->appendTransform(lut);
            }
            group->appendTransform(gp_ocio::definition(s,bake_tone));
            return group;
        };
        const bool has_lut=lut_path && *lut_path;
        try {
            exact=config->getProcessor(definition(false));
            cpu=config->getProcessor(definition(true))->getDefaultCPUProcessor();
        } catch (...) {
            // OCIO caches parsed files, including failed reads, globally by
            // filename. Our canonical snapshot filenames are temporary and
            // unique, so retaining those entries would grow on every slider
            // update. The public API locks its global caches; processors own
            // immutable op data independently. Keep only live snapshots.
            if (has_lut) OCIO::ClearAllCaches();
            throw;
        }
        if (has_lut) OCIO::ClearAllCaches();
    }
};

void fail(char * output, size_t capacity, const char * message) noexcept {
    if (!output || !capacity) return;
    const size_t length=std::min(capacity-1,std::strlen(message));
    std::memcpy(output,message,length);output[length]=0;
}
}

void * gp_ocio_create(const double * parameters, char * error, size_t capacity) {
    return gp_ocio_create_with_lut(parameters,nullptr,error,capacity);
}

void * gp_ocio_create_with_lut(const double * parameters, const char * lut_path, char * error, size_t capacity) {
    try {
        if (!parameters) throw std::invalid_argument("Missing color parameters");
        return new Prepared(parameters,lut_path);
    } catch (const std::exception & e) { fail(error,capacity,e.what()); }
      catch (...) { fail(error,capacity,"OpenColorIO processor preparation failed"); }
    return nullptr;
}

void gp_ocio_destroy(void * processor) {
    delete static_cast<Prepared *>(processor);
}

int gp_ocio_apply(const void * processor, float * r, float * g, float * b,
                  uint32_t width, uint32_t height, size_t r_stride, size_t g_stride,
                  size_t b_stride, char * error, size_t capacity) {
    try {
        if (!processor || !r || !g || !b || !width || !height)
            throw std::invalid_argument("Invalid OpenColorIO image");
        const size_t max_stride=static_cast<size_t>(std::numeric_limits<ptrdiff_t>::max());
        if (height>static_cast<uint32_t>(std::numeric_limits<long>::max()) ||
            width>static_cast<uint32_t>(std::numeric_limits<long>::max()) ||
            r_stride<static_cast<size_t>(width)*4 || g_stride<static_cast<size_t>(width)*4 ||
            b_stride<static_cast<size_t>(width)*4 || r_stride>max_stride ||
            g_stride>max_stride || b_stride>max_stride)
            throw std::invalid_argument("Invalid OpenColorIO row stride");
        const auto & cpu=static_cast<const Prepared *>(processor)->cpu;
        if (r_stride==g_stride && r_stride==b_stride) {
            OCIO::PlanarImageDesc image(r,g,b,nullptr,width,height,
                OCIO::BIT_DEPTH_F32,sizeof(float),static_cast<ptrdiff_t>(r_stride));
            cpu->apply(image);
        } else {
            // OCIO's descriptor has one row stride. Unequal valid FFmpeg plane
            // strides are supported by describing each row independently.
            for (uint32_t y=0;y<height;++y) {
                auto row=[y](float * p,size_t stride) {
                    return reinterpret_cast<float *>(reinterpret_cast<char *>(p)+y*stride);
                };
                OCIO::PlanarImageDesc image(row(r,r_stride),row(g,g_stride),row(b,b_stride),
                    nullptr,width,1,OCIO::BIT_DEPTH_F32,sizeof(float),static_cast<ptrdiff_t>(r_stride));
                cpu->apply(image);
            }
        }
        return 1;
    } catch (const std::exception & e) { fail(error,capacity,e.what()); }
      catch (...) { fail(error,capacity,"OpenColorIO frame processing failed"); }
    return 0;
}

size_t gp_ocio_shader(const void * processor, char * output, size_t output_capacity,
                      char * error, size_t capacity) {
    try {
        if (!processor || !output) throw std::invalid_argument("Missing OpenColorIO shader output");
        auto shader=static_cast<const Prepared *>(processor)->shader();
        std::string text=shader->getShaderText();
        if (shader->getNum3DTextures()) {
            const char * texture,* sampler;unsigned edge;OCIO::Interpolation interpolation;
            shader->get3DTexture(0,texture,sampler,edge,interpolation);
            const std::string declaration=std::string("uniform sampler3D ")+sampler+";";
            const auto position=text.find(declaration);
            if (position==std::string::npos)
                throw std::runtime_error("Unrecognized OpenColorIO sampler declaration");
            text.insert(position,"layout(binding = 2) ");
            const std::string from=sampler,to="ocioLutTexture";
            for (size_t at=0;(at=text.find(from,at))!=std::string::npos;at+=to.size())
                text.replace(at,from.size(),to);
        }
        const size_t length=text.size();
        if (length>output_capacity) throw std::runtime_error("OpenColorIO grading shader exceeds size limit");
        std::memcpy(output,text.data(),length);return length;
    } catch (const std::exception & e) { fail(error,capacity,e.what()); }
      catch (...) { fail(error,capacity,"OpenColorIO preview shader generation failed"); }
    return 0;
}

size_t gp_ocio_texture3d(const void * processor, float * output, size_t float_capacity,
                         uint32_t * edge, char * error, size_t capacity) {
    try {
        if (!processor || !edge) throw std::invalid_argument("Missing OpenColorIO texture output");
        *edge=0;
        auto shader=static_cast<const Prepared *>(processor)->shader();
        if (!shader->getNum3DTextures()) return 0;
        const char * texture,* sampler;unsigned size;OCIO::Interpolation interpolation;
        shader->get3DTexture(0,texture,sampler,size,interpolation);
        *edge=size;
        const size_t count=static_cast<size_t>(size)*size*size*3;
        if (!output && !float_capacity) return count;
        if (!output || float_capacity<count) throw std::invalid_argument("OpenColorIO texture output too small");
        const float * values=nullptr;shader->get3DTextureValues(0,values);
        if (!values) throw std::runtime_error("Missing OpenColorIO texture values");
        std::copy(values,values+count,output);return count;
    } catch (const std::exception & e) { fail(error,capacity,e.what()); }
      catch (...) { fail(error,capacity,"OpenColorIO preview texture extraction failed"); }
    return 0;
}
