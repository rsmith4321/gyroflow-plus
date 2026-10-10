// SPDX-License-Identifier: GPL-3.0-or-later
// Isolated C ABI contract/concurrency checks. This is not Rust layout validation,
// app preview, real-video, encoder or portable-package acceptance.
#include "../../src/rendering/ocio/bridge.h"
#include "../../src/rendering/ocio/grade.hpp"
extern "C" {
#include <libavutil/frame.h>
#include <libavutil/pixfmt.h>
}
#include <array>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <random>
#include <stdexcept>
#include <thread>
#include <vector>

namespace {
namespace OCIO = OCIO_NAMESPACE;
constexpr uint32_t width = 167, height = 17;
constexpr size_t guard = 8;
constexpr float sentinel = -123.5f;

void require(bool value, const char * message) {
    if (!value) throw std::runtime_error(message);
}

struct Planes {
    std::array<size_t, 3> strides;
    std::array<std::vector<float>, 3> data;
    explicit Planes(std::array<size_t, 3> rows = {174, 174, 174}) : strides(rows) {
        for (size_t p = 0; p < 3; ++p) {
            data[p].assign(2 * guard + strides[p] * height, sentinel);
            for (size_t y = 0; y < height; ++y)
                for (size_t x = 0; x < width; ++x)
                    data[p][guard + y * strides[p] + x] = float((p + x + y) % 13) / 12;
        }
    }
    float * plane(size_t p) { return data[p].data() + guard; }
    float sample(size_t p, size_t x, size_t y) const { return data[p][guard + y * strides[p] + x]; }
    void check_guards() const {
        for (size_t p = 0; p < 3; ++p) {
            for (size_t i = 0; i < guard; ++i) {
                require(data[p][i] == sentinel, "Prefix guard changed");
                require(data[p][guard + strides[p] * height + i] == sentinel, "Suffix guard changed");
            }
            for (size_t y = 0; y < height; ++y)
                for (size_t x = width; x < strides[p]; ++x)
                    require(data[p][guard + y * strides[p] + x] == sentinel, "Row padding changed");
        }
    }
};

void apply(const void * processor, Planes & image) {
    char error[4096] = {};
    const auto & s = image.strides;
    require(gp_ocio_apply(processor, image.plane(0), image.plane(1), image.plane(2),
        width, height, s[0] * sizeof(float), s[1] * sizeof(float), s[2] * sizeof(float),
        error, sizeof(error)) == 1, error);
    image.check_guards();
}

struct Processor {
    void * handle;
    explicit Processor(const std::array<double, 8> & parameters, const char * lut = nullptr) : handle(nullptr) {
        char error[4096] = {};
        handle = lut ? gp_ocio_create_with_lut(parameters.data(), lut, error, sizeof(error))
                     : gp_ocio_create(parameters.data(), error, sizeof(error));
        require(handle != nullptr, error);
    }
    ~Processor() { gp_ocio_destroy(handle); }
    Processor(const Processor &) = delete;
    Processor & operator=(const Processor &) = delete;
};

void negative_stride_contract() {
    // av_frame_make_writable does not normalize a writable negative-stride
    // image. Rust must inspect signed raw linesizes before ffmpeg-next's data()
    // wrappers. This demonstrates that precondition; it does not call the Rust
    // validator and does not pass invalid unsigned strides to OCIO.
    AVFrame * frame = av_frame_alloc();
    require(frame != nullptr, "Cannot allocate AVFrame");
    frame->format = AV_PIX_FMT_GBRPF32LE;
    frame->width = 17; frame->height = 5;
    if (av_frame_get_buffer(frame, 32) != 0) {
        av_frame_free(&frame); throw std::runtime_error("Cannot allocate frame data");
    }
    for (int p = 0; p < 3; ++p) {
        frame->data[p] += (frame->height - 1) * frame->linesize[p];
        frame->linesize[p] = -frame->linesize[p];
    }
    const int stride = frame->linesize[0];
    const int result = av_frame_make_writable(frame);
    const bool retained = frame->linesize[0] == stride && stride < 0;
    av_frame_free(&frame);
    require(result == 0 && retained, "Expected writable negative stride contract changed");
}

void rejected_parameters() {
    const std::array<double, 8> limits = {.5, .5, .5, .5, 2, 1, 1, 1};
    for (size_t p = 0; p < limits.size(); ++p) {
        for (double invalid : {std::numeric_limits<double>::quiet_NaN(),
                std::numeric_limits<double>::infinity(), -limits[p] - .01, limits[p] + .01}) {
            std::array<double, 8> settings = {};
            settings[p] = invalid;
            // Error output must stay within a capacity of two bytes and end in
            // NUL even when the upstream exception message is much longer.
            char buffer[4] = {'L', '?', '?', 'R'};
            void * handle = gp_ocio_create(settings.data(), buffer + 1, 2);
            if (handle) gp_ocio_destroy(handle);
            require(handle == nullptr, "Invalid parameter accepted");
            require(buffer[0] == 'L' && buffer[2] == 0 && buffer[3] == 'R', "Error buffer bounds changed");
        }
    }
    char error[16] = {};
    require(gp_ocio_create(nullptr, error, sizeof(error)) == nullptr && error[0] != 0,
        "Missing parameters accepted");
    require(gp_ocio_create(nullptr, nullptr, 0) == nullptr, "Null error buffer was not supported");
    gp_ocio_destroy(nullptr);
}

struct TemporaryLut {
    std::filesystem::path directory, path;
    explicit TemporaryLut(bool extended_output = false) {
        std::random_device random;
        directory = std::filesystem::temp_directory_path() /
            ("gyroflow-ocio-bridge-check-" + std::to_string(random()) + "-" + std::to_string(random()));
        require(std::filesystem::create_directory(directory), "Cannot create private LUT fixture directory");
        path = directory / "nonlinear.cube";
        std::ofstream file(path);
        // Canonical supported input: bounded 3D table, standard 0–1 domain,
        // red fastest. Each output is nonlinear and mixes at least two channels.
        file << "LUT_3D_SIZE 3\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n";
        for (int b = 0; b < 3; ++b) for (int g = 0; g < 3; ++g) for (int r = 0; r < 3; ++r) {
            const double red = r / 2.0, green = g / 2.0, blue = b / 2.0;
            const std::array<double, 3> values = {.1 + .55 * red + .1 * green * blue,
                .03 + .57 * green * green + .19 * red * blue, .11 + .35 * blue + .23 * red * green};
            for (size_t p = 0; p < 3; ++p)
                file << (extended_output ? values[p] * 2 - .3 : values[p]) << (p == 2 ? '\n' : ' ');
        }
        require(static_cast<bool>(file), "Cannot write bounded cube fixture");
        file.close();
        require(std::filesystem::file_size(path) < 4096, "Fixture LUT exceeded intended bound");
    }
    ~TemporaryLut() { std::error_code ignored; std::filesystem::remove_all(directory, ignored); }
    TemporaryLut(const TemporaryLut &) = delete;
    TemporaryLut & operator=(const TemporaryLut &) = delete;
};

std::vector<float> packed(const Planes & image) {
    std::vector<float> result(size_t(width) * height * 4);
    for (size_t y = 0; y < height; ++y) for (size_t x = 0; x < width; ++x) {
        const size_t i = (y * width + x) * 4;
        for (size_t p = 0; p < 3; ++p) result[i + p] = image.sample(p, x, y);
        result[i + 3] = float((x + y) % 11) / 10;
    }
    return result;
}

void official_apply(const OCIO::ConstCPUProcessorRcPtr & cpu, std::vector<float> & image,
        long image_width = width, long image_height = height) {
    OCIO::PackedImageDesc descriptor(image.data(), image_width, image_height, 4);
    cpu->apply(descriptor);
}

double lut_order_and_errors(bool extended_output) {
    TemporaryLut file(extended_output);
    const auto path = file.path.string();
    const std::array<double, 8> controls = {.12, .18, .3, -.4, .37, .23, .41, -.27};
    const gp_ocio::Settings settings{controls[0], controls[1], controls[2], controls[3],
        controls[4], controls[5], controls[6], controls[7]};
    auto config = OCIO::Config::CreateRaw();
    auto lut = OCIO::FileTransform::Create();
    lut->setSrc(path.c_str()); lut->setInterpolation(OCIO::INTERP_TETRAHEDRAL);
    const auto lut_cpu = config->getProcessor(lut)->getDefaultCPUProcessor();
    const auto grade_cpu = config->getProcessor(gp_ocio::definition(settings, true))->getDefaultCPUProcessor();
    const Planes original;
    const auto original_packed = packed(original);
    auto expected = original_packed;
    // Independent composition of the two official processors proves ordering,
    // rather than comparing the bridge with its own combined transform.
    official_apply(lut_cpu, expected);
    const auto lut_only = expected;
    official_apply(grade_cpu, expected);
    auto wrong_order = original_packed;
    official_apply(grade_cpu, wrong_order); official_apply(lut_cpu, wrong_order);
    Processor combined(controls, path.c_str()), selected({}, path.c_str());
    Planes actual = original, selected_output = original;
    apply(combined.handle, actual); apply(selected.handle, selected_output);
    double error = 0, order_difference = 0;
    bool outside = false;
    for (size_t y = 0; y < height; ++y) for (size_t x = 0; x < width; ++x) {
        const size_t i = (y * width + x) * 4;
        require(expected[i + 3] == original_packed[i + 3] && lut_only[i + 3] == original_packed[i + 3],
            "Official LUT/grade altered packed alpha");
        for (size_t p = 0; p < 3; ++p) {
            error = std::max(error, double(std::abs(actual.sample(p, x, y) - expected[i + p])));
            order_difference = std::max(order_difference, double(std::abs(wrong_order[i + p] - expected[i + p])));
            require(std::abs(selected_output.sample(p, x, y) - lut_only[i + p]) <= 1e-6f,
                "LUT-only bridge differs from official tetrahedral FileTransform");
            outside = outside || lut_only[i + p] < 0 || lut_only[i + p] > 1;
        }
    }
    require(error <= 1e-6, "Combined LUT/grade did not match LUT-first official composition");
    require(order_difference > .01, "LUT-order negative control was ineffective");
    if (extended_output) require(outside, "Extended-output LUT fixture did not exercise out-of-range values");

    char message[4096] = {};
    auto bad = file.directory / "missing.cube";
    void * rejected = gp_ocio_create_with_lut(controls.data(), bad.string().c_str(), message, sizeof(message));
    if (rejected) gp_ocio_destroy(rejected);
    require(rejected == nullptr && message[0], "Missing LUT path was accepted without error");
    bad = file.directory / "malformed.cube";
    { std::ofstream broken(bad); broken << "LUT_3D_SIZE 3\n0 0 0\n"; }
    rejected = gp_ocio_create_with_lut(controls.data(), bad.string().c_str(), message, sizeof(message));
    if (rejected) gp_ocio_destroy(rejected);
    require(rejected == nullptr && message[0], "Incomplete LUT was accepted without error");
    Processor empty_path({}, "");
    Planes unchanged = original;
    apply(empty_path.handle, unchanged);
    require(unchanged.data == original.data, "Empty LUT path changed neutral behavior");
    // The prepared processors own loaded LUT operations; no apply-time filename
    // access is needed. Remove the source before reapplying the snapshot.
    require(std::filesystem::remove(file.path), "Cannot remove prepared LUT source");
    Planes after_remove = original;
    apply(combined.handle, after_remove);
    require(after_remove.data == actual.data, "Prepared processor depended on a later LUT file read");
    return error;
}

double dense_tone_error() {
    // 16 subdivisions per baked LUT interval, plus exact/adjacent float values
    // around public VIDEO shadow/highlight starts, pivots and midpoints. These
    // values come from the public parameter struct, not copied curve internals.
    std::vector<float> values;
    for (size_t i = 0; i <= 65536; ++i) values.push_back(float(i) / 65536);
    const OCIO::GradingTone defaults(OCIO::GRADING_VIDEO);
    for (double center : {0., 1., defaults.m_shadows.m_start, defaults.m_shadows.m_width,
            defaults.m_highlights.m_start, defaults.m_highlights.m_width,
            (defaults.m_shadows.m_start + defaults.m_shadows.m_width) * .5,
            (defaults.m_highlights.m_start + defaults.m_highlights.m_width) * .5}) {
        const float c = float(center);
        values.push_back(c);
        values.push_back(std::nextafter(c, -std::numeric_limits<float>::infinity()));
        values.push_back(std::nextafter(c, std::numeric_limits<float>::infinity()));
        for (float delta : {-1.f / 4096, -1.f / 8192, -1e-7f, 1e-7f, 1.f / 8192, 1.f / 4096})
            values.push_back(c + delta);
    }
    values.push_back(-.1f); values.push_back(1.1f);
    std::sort(values.begin(), values.end());
    values.erase(std::unique(values.begin(), values.end()), values.end());
    std::vector<float> source(values.size() * 4);
    for (size_t i = 0; i < values.size(); ++i) {
        source[i * 4] = values[i]; source[i * 4 + 1] = 1 - values[i];
        source[i * 4 + 2] = .137f + .726f * values[i]; source[i * 4 + 3] = float(i % 11) / 10;
    }
    const std::array<double, 7> amounts = {-.5, -.317, -.001, 0, .001, .219, .5};
    double maximum = 0;
    double worst_shadows = 0, worst_highlights = 0;
    bool worst_combined = false;
    size_t worst_pixel = 0, worst_channel = 0;
    unsigned cases = 0;
    for (double shadows : amounts) for (double highlights : amounts) for (bool combined : {false, true}) {
        // Match the production snapshot lifecycle. Reusing one OCIO Config for
        // different same-size in-memory LUTs can reuse a processor keyed by the
        // streamed transform description, which omits full Lut1D entry data.
        auto config = OCIO::Config::CreateRaw();
        const gp_ocio::Settings settings{combined ? .12 : 0, combined ? .18 : 0, shadows, highlights,
            combined ? .37 : 0, combined ? 1. : 0., combined ? .41 : 0, combined ? -.27 : 0};
        const auto exact = config->getProcessor(gp_ocio::definition(settings))->getDefaultCPUProcessor();
        const auto baked = config->getProcessor(gp_ocio::definition(settings, true))->getDefaultCPUProcessor();
        auto reference = source, actual = source;
        official_apply(exact, reference, long(values.size()), 1);
        official_apply(baked, actual, long(values.size()), 1);
        // Recreate the actual production bridge for each distinct snapshot. A
        // future shared-Config cache must not return a previous sampled curve.
        Processor snapshot({settings.brightness, settings.contrast, settings.shadows, settings.highlights,
            settings.exposure, settings.saturation, settings.warmth, settings.tint});
        std::array<std::vector<float>, 3> bridge_planes;
        for (size_t p = 0; p < 3; ++p) {
            bridge_planes[p].resize(values.size());
            for (size_t i = 0; i < values.size(); ++i) bridge_planes[p][i] = source[i * 4 + p];
        }
        char message[4096] = {};
        const size_t stride_bytes = values.size() * sizeof(float);
        require(gp_ocio_apply(snapshot.handle, bridge_planes[0].data(), bridge_planes[1].data(), bridge_planes[2].data(),
            uint32_t(values.size()), 1, stride_bytes, stride_bytes, stride_bytes, message, sizeof(message)) == 1, message);
        for (size_t i = 0; i < values.size(); ++i) {
            require(reference[i * 4 + 3] == source[i * 4 + 3] && actual[i * 4 + 3] == source[i * 4 + 3],
                "Dense tone processing altered packed alpha");
            for (size_t p = 0; p < 3; ++p) {
                require(std::abs(bridge_planes[p][i] - actual[i * 4 + p]) <= 2e-7f,
                    "Production snapshot did not match fresh official cached-tone processor");
                require(std::isfinite(reference[i * 4 + p]) && std::isfinite(actual[i * 4 + p]),
                    "Dense tone processing produced nonfinite output");
                const double error = std::abs(actual[i * 4 + p] - reference[i * 4 + p]);
                if (error > maximum) {
                    maximum = error; worst_shadows = shadows; worst_highlights = highlights;
                    worst_combined = combined; worst_pixel = i; worst_channel = p;
                }
            }
        }
        ++cases;
    }
    std::cout << "dense_tone: cases=" << cases << " samples_per_case=" << values.size()
        << " float_max_error=" << maximum << " shadows=" << worst_shadows << " highlights=" << worst_highlights
        << " combined=" << worst_combined << " input_r=" << values[worst_pixel]
        << " channel=" << worst_channel << '\n';
    require(maximum <= 1e-5, "Dense cached-tone error exceeded existing floating-point tolerance");
    return maximum;
}

std::string shader_text(const void * processor) {
    std::vector<char> output(256 * 1024);
    char message[4096] = {};
    const size_t count = gp_ocio_shader(processor, output.data(), output.size(), message, sizeof(message));
    require(count > 0 && count <= output.size(), message);
    return std::string(output.data(), count);
}

std::pair<uint32_t, std::vector<float>> texture_values(const void * processor) {
    char message[4096] = {};
    uint32_t edge = 0;
    const size_t count = gp_ocio_texture3d(processor, nullptr, 0, &edge, message, sizeof(message));
    require(message[0] == 0 && edge >= 2 && edge <= 128 && count == size_t(edge) * edge * edge * 3,
        "Invalid 3D texture size query");
    std::vector<float> data(count + 2, sentinel);
    require(gp_ocio_texture3d(processor, data.data() + 1, count, &edge, message, sizeof(message)) == count,
        "3D texture copy failed");
    require(data.front() == sentinel && data.back() == sentinel, "3D texture copy changed guards");
    return {edge, std::vector<float>(data.begin() + 1, data.end() - 1)};
}

void gpu_resource_contracts() {
    TemporaryLut file(true);
    const auto path = file.path.string();
    const std::array<double, 8> controls = {.12, .18, .3, -.4, .37, .23, .41, -.27};
    Processor serial(controls, path.c_str());
    const auto expected_text = shader_text(serial.handle);
    const auto expected_texture = texture_values(serial.handle);
    require(expected_text.find("layout(binding = 2) uniform sampler3D ocioLutTexture;") != std::string::npos,
        "Generated LUT sampler was not normalized to binding 2");

    // Compare copied resource data with an independent official GPU descriptor,
    // including its layout and interpolation metadata, without rendering it.
    auto config = OCIO::Config::CreateRaw();
    auto definition = OCIO::GroupTransform::Create();
    auto domain = OCIO::RangeTransform::Create();
    domain->setMinInValue(0); domain->setMinOutValue(0); domain->setMaxInValue(1); domain->setMaxOutValue(1);
    definition->appendTransform(domain);
    auto lut = OCIO::FileTransform::Create();
    lut->setSrc(path.c_str()); lut->setInterpolation(OCIO::INTERP_TETRAHEDRAL);
    definition->appendTransform(lut);
    definition->appendTransform(gp_ocio::definition({controls[0], controls[1], controls[2], controls[3],
        controls[4], controls[5], controls[6], controls[7]}));
    auto descriptor = OCIO::GpuShaderDesc::CreateShaderDesc();
    descriptor->setLanguage(OCIO::GPU_LANGUAGE_GLSL_4_0);
    descriptor->setFunctionName("applyOcioGrade"); descriptor->setResourcePrefix("gp_ocio_");
    descriptor->setAllowTexture1D(false);
    config->getProcessor(definition)->getDefaultGPUProcessor()->extractGpuShaderInfo(descriptor);
    require(descriptor->getNum3DTextures() == 1 && descriptor->getNumTextures() == 0 && descriptor->getNumUniforms() == 0,
        "Official resource count did not match supported layout");
    const char * texture_name, * sampler_name;
    unsigned official_edge; OCIO::Interpolation interpolation;
    descriptor->get3DTexture(0, texture_name, sampler_name, official_edge, interpolation);
    const float * official_values = nullptr;
    descriptor->get3DTextureValues(0, official_values);
    require(official_values && official_edge == expected_texture.first && interpolation == OCIO::INTERP_NEAREST,
        "Copied texture layout differs from official GPU descriptor");
    require(std::equal(expected_texture.second.begin(), expected_texture.second.end(), official_values),
        "Copied texture values/order differ from official GPU descriptor");
    require(expected_text.find(sampler_name) == std::string::npos, "Original sampler name was left in normalized GLSL");

    // Exercise simultaneous first access to the lazy descriptor through both ABI
    // entry points. Each call owns its output buffers; all extraction is exact.
    Processor concurrent(controls, path.c_str());
    std::atomic<bool> start{false};
    std::atomic<unsigned> errors{0};
    std::vector<std::thread> threads;
    for (int t = 0; t < 8; ++t) threads.emplace_back([&, t] {
        while (!start.load()) std::this_thread::yield();
        for (int n = 0; n < 50; ++n) {
            try {
                if (t % 2 == 0) {
                    if (shader_text(concurrent.handle) != expected_text) ++errors;
                    if (texture_values(concurrent.handle) != expected_texture) ++errors;
                } else {
                    if (texture_values(concurrent.handle) != expected_texture) ++errors;
                    if (shader_text(concurrent.handle) != expected_text) ++errors;
                }
            } catch (...) { ++errors; }
        }
    });
    start = true;
    for (auto & thread : threads) thread.join();
    require(errors == 0, "Concurrent first extraction differed from serial GPU resources");

    char message[4096] = {};
    uint32_t edge = 999;
    const size_t count = expected_texture.second.size();
    std::vector<float> small(count + 2, sentinel);
    require(gp_ocio_texture3d(serial.handle, small.data() + 1, count - 1, &edge, message, sizeof(message)) == 0
        && message[0] != 0, "Small 3D texture output was accepted");
    require(std::all_of(small.begin(), small.end(), [](float value) { return value == sentinel; }),
        "Rejected 3D texture copy modified output");
    message[0] = 0;
    require(gp_ocio_texture3d(serial.handle, nullptr, count, &edge, message, sizeof(message)) == 0
        && message[0] != 0, "Null 3D copy output with nonzero capacity was accepted");
    message[0] = 0;
    require(gp_ocio_texture3d(serial.handle, nullptr, 0, nullptr, message, sizeof(message)) == 0
        && message[0] != 0, "Missing 3D edge output was accepted");
    message[0] = 0;
    require(gp_ocio_texture3d(nullptr, nullptr, 0, &edge, message, sizeof(message)) == 0
        && message[0] != 0, "Missing resource processor was accepted");
    char tiny_shader[4] = {'L', '?', '?', 'R'};
    require(gp_ocio_shader(serial.handle, tiny_shader + 1, 2, message, sizeof(message)) == 0
        && tiny_shader[0] == 'L' && tiny_shader[3] == 'R', "Small LUT shader copy changed guards");
    message[0] = 0;
    require(gp_ocio_shader(serial.handle, nullptr, 0, message, sizeof(message)) == 0
        && message[0] != 0, "Missing shader output was accepted");

    Processor grade_only(controls);
    message[0] = 0; edge = 999;
    require(gp_ocio_texture3d(grade_only.handle, nullptr, 0, &edge, message, sizeof(message)) == 0
        && edge == 0 && message[0] == 0, "Grade-only shader unexpectedly returned a 3D resource/error");
    require(shader_text(grade_only.handle).find("sampler3D") == std::string::npos,
        "Grade-only shader unexpectedly declared a 3D sampler");
    std::cout << "gpu_resources: 400 concurrent first-access shader/texture extractions match serial output; "
        "official descriptor order, binding, null/capacity and no-LUT contracts passed\n";
}

void cache_clear_lifetime_contract() {
    TemporaryLut retained_file(true);
    const auto retained_path = retained_file.path.string();
    const std::array<double, 8> controls = {.12, .18, .3, -.4, .37, .23, .41, -.27};
    Processor serial(controls, retained_path.c_str()), retained(controls, retained_path.c_str());
    const auto expected_shader = shader_text(serial.handle);
    const auto expected_texture = texture_values(serial.handle);
    const Planes original;
    Planes expected = original;
    apply(serial.handle, expected);
    // Retained has never extracted GPU resources. Its first extraction must use
    // owned op data after global filename caches and the source file are gone.
    require(std::filesystem::remove(retained_file.path), "Cannot remove retained LUT source");

    std::atomic<bool> start{false}, cleared{false}, first_gpu_started{false}, stop{false}, done{false};
    std::atomic<unsigned> errors{0}, completed{0}, repaired{0};
    std::thread clearing([&] {
        while (!start.load()) std::this_thread::yield();
        try {
            for (unsigned n = 0; n < 64 && !stop.load(); ++n) {
                TemporaryLut fresh(n % 2 != 0);
                auto settings = controls;
                settings[0] += .001 * (n % 3);
                const auto path = fresh.path.string();
                Processor snapshot(settings, path.c_str()); // Constructor clears global caches.
                Planes fresh_expected = original;
                apply(snapshot.handle, fresh_expected);

                if (n % 8 == 0) {
                    for (bool incomplete : {false, true}) {
                        const auto failed_path = fresh.directory /
                            (incomplete ? "incomplete.cube" : "missing.cube");
                        if (incomplete) {
                            std::ofstream broken(failed_path);
                            broken << "LUT_3D_SIZE 3\n0 0 0\n";
                            require(static_cast<bool>(broken), "Cannot write incomplete cache fixture");
                        }
                        char message[4096] = {};
                        void * rejected = gp_ocio_create_with_lut(settings.data(),
                            failed_path.string().c_str(), message, sizeof(message));
                        if (rejected) gp_ocio_destroy(rejected);
                        require(rejected == nullptr && message[0], "Failed LUT snapshot was accepted");
                        // Reusing the same failed filename after repair catches
                        // retained negative path/file entries, not just crashes.
                        std::filesystem::copy_file(fresh.path, failed_path,
                            std::filesystem::copy_options::overwrite_existing);
                        Processor recovered(settings, failed_path.string().c_str());
                        Planes actual = original;
                        apply(recovered.handle, actual);
                        require(actual.data == fresh_expected.data,
                            "Repaired LUT path reused failed or stale cached data");
                        ++repaired;
                    }
                }
                ++completed;
                if (n == 0) {
                    cleared = true;
                    // Start the remaining clears with the retained processor's
                    // first lazy GPU extraction, rather than after it finishes.
                    while (!first_gpu_started.load() && !stop.load()) std::this_thread::yield();
                }
            }
        } catch (...) { ++errors; }
        done = true;
    });

    std::exception_ptr reader_error;
    start = true;
    try {
        while (!cleared.load() && !done.load()) std::this_thread::yield();
        require(cleared.load(), "Concurrent snapshot failed before first cache clear");
        first_gpu_started = true;
        require(shader_text(retained.handle) == expected_shader,
            "Retained first GPU shader changed after global cache clear");
        require(texture_values(retained.handle) == expected_texture,
            "Retained first GPU texture changed after global cache clear");
        for (unsigned n = 0; n < 128; ++n) {
            Planes actual = original;
            apply(retained.handle, actual);
            require(actual.data == expected.data, "Retained CPU output changed during global cache clears");
        }
    } catch (...) {
        reader_error = std::current_exception();
        stop = true;
        first_gpu_started = true;
    }
    clearing.join();
    if (reader_error) std::rethrow_exception(reader_error);
    require(errors == 0 && completed == 64 && repaired == 16,
        "Concurrent cache-clear snapshot construction or failed-path recovery failed");
    Planes after_clear = original;
    apply(retained.handle, after_clear);
    require(after_clear.data == expected.data && shader_text(retained.handle) == expected_shader
        && texture_values(retained.handle) == expected_texture,
        "Retained CPU/GPU resources changed after snapshot destruction");
    std::cout << "cache_lifetime: retained CPU and first lazy GPU resources survive 64 concurrent "
        "LUT snapshots and 16 rejected/repaired missing or incomplete reads\n";
}
}

int main() {
    try {
        negative_stride_contract();
        rejected_parameters();
        std::cout << "lut_order: bounded_max_error=" << lut_order_and_errors(false)
            << " extended_output_max_error=" << lut_order_and_errors(true) << '\n';
        dense_tone_error();
        gpu_resource_contracts();
        cache_clear_lifetime_contract();
        Processor processor({.12, .18, .3, -.4, .37, .23, .41, -.27});
        Planes original, expected;
        apply(processor.handle, expected);
        require(original.data != expected.data, "Combined grade was bypassed");

        // Share one immutable official CPU processor across eight actual threads.
        // Every call owns disjoint buffers; compare every byte with serial output.
        std::atomic<unsigned> errors{0};
        std::vector<std::thread> threads;
        for (int t = 0; t < 8; ++t) threads.emplace_back([&] {
            for (int n = 0; n < 100; ++n) {
                try {
                    Planes image = original;
                    apply(processor.handle, image);
                    if (image.data != expected.data) ++errors;
                } catch (...) { ++errors; }
            }
        });
        for (auto & thread : threads) thread.join();
        require(errors == 0, "Concurrent processor differed from serial output");

        Planes unequal({174, 177, 181});
        apply(processor.handle, unequal);
        for (size_t p = 0; p < 3; ++p)
            for (size_t y = 0; y < height; ++y)
                for (size_t x = 0; x < width; ++x)
                    require(unequal.sample(p, x, y) == expected.sample(p, x, y),
                        "Unequal-stride output differed from equal-stride output");

        Processor neutral({});
        Planes unchanged = original;
        apply(neutral.handle, unchanged);
        require(unchanged.data == original.data, "Neutral processor changed pixels or padding");

        char error[4096] = {};
        char tiny[8] = {};
        require(gp_ocio_shader(processor.handle, tiny, sizeof(tiny), error, sizeof(error)) == 0
            && error[0] != 0, "Small shader buffer accepted");
        std::vector<char> shader(256 * 1024);
        require(gp_ocio_shader(processor.handle, shader.data(), shader.size(), error, sizeof(error)) > 0,
            "Shader extraction failed");
        require(gp_ocio_shader(nullptr, shader.data(), shader.size(), error, sizeof(error)) == 0,
            "Missing shader processor accepted");
        Planes rejected = original;
        require(gp_ocio_apply(processor.handle, rejected.plane(0), rejected.plane(1), rejected.plane(2),
            width, height, width * 4 - 1, 174 * 4, 174 * 4, error, sizeof(error)) == 0,
            "Short row stride accepted");
        require(gp_ocio_apply(nullptr, rejected.plane(0), rejected.plane(1), rejected.plane(2),
            width, height, 174 * 4, 174 * 4, 174 * 4, error, sizeof(error)) == 0,
            "Missing apply processor accepted");
        require(gp_ocio_apply(processor.handle, rejected.plane(0), rejected.plane(1), rejected.plane(2),
            0, height, 174 * 4, 174 * 4, 174 * 4, error, sizeof(error)) == 0,
            "Empty image accepted");
        require(rejected.data == original.data, "Rejected image was modified");

        std::cout << "bridge_check: 800 concurrent calls match serial output; unequal strides, "
            "neutral, guards/padding, 32 invalid parameters, error bounds, shader capacities "
            "and writable negative-stride contract passed\n";
        return 0;
    } catch (const std::exception & error) {
        std::cerr << "bridge_check: " << error.what() << '\n'; return 1;
    }
}
