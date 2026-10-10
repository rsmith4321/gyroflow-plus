// SPDX-License-Identifier: GPL-3.0-or-later
// Synthetic native GPU acceptance. No user video, application, or preferences.
#include <QGuiApplication>
#include <QQmlComponent>
#include <QQuickRenderControl>
#include <QQuickRenderTarget>
#include <QJsonArray>
#include <QTextStream>
#include <array>
#include <algorithm>
#include <cstring>
#include <iostream>
#include <numeric>
#include <thread>
#include "../../src/qt_gpu/ocio_preview.cpp"
#include "../../src/rendering/ocio/bridge.h"

static void require(bool condition, const std::string & message) {
    if (!condition) throw std::runtime_error(message);
}
class InputTexture final : public QSGTexture {
    QSize m_size;
    std::vector<float> m_pixels;
    std::unique_ptr<QRhiTexture> m_texture;
public:
    InputTexture(QSize size, std::vector<float> pixels) : m_size(size), m_pixels(std::move(pixels)) {
        setFiltering(Nearest); setHorizontalWrapMode(ClampToEdge); setVerticalWrapMode(ClampToEdge);
    }
    qint64 comparisonKey() const override { return qint64(reinterpret_cast<quintptr>(this)); }
    QRhiTexture * rhiTexture() const override { return m_texture.get(); }
    QSize textureSize() const override { return m_size; }
    bool hasAlphaChannel() const override { return false; }
    bool hasMipmaps() const override { return false; }
    void commitTextureOperations(QRhi * rhi, QRhiResourceUpdateBatch * updates) override {
        if (m_texture) return;
        m_texture.reset(rhi->newTexture(QRhiTexture::RGBA32F, m_size));
        require(m_texture->create(), "Cannot create float32 fixture input texture");
        QRhiTextureSubresourceUploadDescription pixels(m_pixels.data(), quint32(m_pixels.size() * sizeof(float)));
        pixels.setSourceSize(m_size);
        pixels.setDataStride(quint32(m_size.width() * 4 * sizeof(float)));
        updates->uploadTexture(m_texture.get(), QRhiTextureUploadDescription({QRhiTextureUploadEntry(0, 0, pixels)}));
    }
};
class InputProvider final : public QSGTextureProvider {
    std::unique_ptr<InputTexture> m_texture;
public:
    InputProvider(QSize size, const std::vector<float> & pixels) : m_texture(new InputTexture(size, pixels)) {}
    QSGTexture * texture() const override { return m_texture.get(); }
};
class InputItem final : public QQuickItem {
    QSize m_size;
    std::vector<float> m_pixels;
    mutable std::unique_ptr<InputProvider> m_provider;
public:
    InputItem(QQuickWindow * window, QSize size, std::vector<float> pixels) : QQuickItem(window->contentItem()), m_size(size), m_pixels(std::move(pixels)) {
        QObject::connect(window, &QQuickWindow::sceneGraphInvalidated, this, [this] { m_provider.reset(); }, Qt::DirectConnection);
    }
    bool isTextureProvider() const override { return true; }
    QSGTextureProvider * textureProvider() const override {
        if (!m_provider) m_provider.reset(new InputProvider(m_size, m_pixels));
        return m_provider.get();
    }
};
#if defined(Q_OS_WIN)
static constexpr QRhi::Implementation expectedBackend = QRhi::D3D11;
static constexpr QSGRendererInterface::GraphicsApi expectedGraphicsApi = QSGRendererInterface::Direct3D11;
static constexpr const char * backendName = "D3D11";
#elif defined(Q_OS_MACOS)
static constexpr QRhi::Implementation expectedBackend = QRhi::Metal;
static constexpr QSGRendererInterface::GraphicsApi expectedGraphicsApi = QSGRendererInterface::Metal;
static constexpr const char * backendName = "Metal";
#else
static constexpr QRhi::Implementation expectedBackend = QRhi::OpenGLES2;
static constexpr QSGRendererInterface::GraphicsApi expectedGraphicsApi = QSGRendererInterface::OpenGL;
static constexpr const char * backendName = "OpenGL";
#endif
struct NativeFixture {
    QQuickRenderControl control;
    QQuickWindow window{&control};
    QQmlEngine engine;
    std::unique_ptr<QRhiTexture> target;
    std::unique_ptr<QRhiTextureRenderTarget> renderTarget;
    std::unique_ptr<QRhiRenderPassDescriptor> renderPass;
    InputItem * input = nullptr;
    QQuickItem * effect = nullptr;
    QObject * lut = nullptr;
    QSize size;
    explicit NativeFixture(const std::vector<float> & pixels) : size(int(pixels.size() / 4), 1) {
        window.setGeometry(0, 0, size.width(), size.height());
        window.setColor(Qt::transparent);
        require(control.initialize(), "QQuickRenderControl initialization failed");
        require(control.rhi() && control.rhi()->backend() == expectedBackend, std::string("Native fixture did not initialize ") + backendName);
        std::cout << "backend=" << backendName << " device=" << control.rhi()->driverInfo().deviceName.constData() << "\n";
        initializeTarget();
        input = new InputItem(&window, size, pixels);
        QQmlComponent component(&engine);
        component.setData(R"QML(import QtQuick
ShaderEffect {
    property var source
    property var ocioLutTexture
    property string ocioPreviewError: ""
    property string ocioPreviewTextureToken: ""
    blending: false
})QML", QUrl());
        QObject * object = component.create();
        require(object != nullptr, component.errorString().toStdString());
        effect = qobject_cast<QQuickItem *>(object);
        require(effect != nullptr, "Fixture ShaderEffect was not an item");
        effect->setParentItem(window.contentItem());
        effect->setParent(&window);
        effect->setSize(QSizeF(size));
        effect->setProperty("source", QVariant::fromValue(static_cast<QObject *>(input)));
    }
    void initializeTarget() {
        target.reset(control.rhi()->newTexture(QRhiTexture::RGBA32F, size, 1, QRhiTexture::RenderTarget | QRhiTexture::UsedAsTransferSource));
        require(target->create(), "Cannot create float32 readback render target");
        renderTarget.reset(control.rhi()->newTextureRenderTarget({QRhiColorAttachment(target.get())}));
        renderPass.reset(renderTarget->newCompatibleRenderPassDescriptor());
        renderTarget->setRenderPassDescriptor(renderPass.get());
        require(renderTarget->create(), "Cannot create fixture render target");
        window.setRenderTarget(QQuickRenderTarget::fromRhiRenderTarget(renderTarget.get()));
    }
    void recreate() {
        control.rhi()->finish();
        window.setRenderTarget(QQuickRenderTarget());
        renderTarget.reset(); renderPass.reset(); target.reset();
        control.invalidate();
        require(control.initialize(), "Native scenegraph reinitialization failed");
        require(control.rhi()->backend() == expectedBackend, "Native backend changed on recreation");
        initializeTarget();
    }
    ~NativeFixture() {
        control.invalidate(); // Render-thread resource deletion precedes QRhi teardown.
        delete effect; delete input;
        window.setRenderTarget(QQuickRenderTarget());
        renderTarget.reset(); renderPass.reset(); target.reset();
    }
    void bind(const QString & source, const QString & token) {
        effect->setProperty("ocioPreviewError", "");
        effect->setProperty("ocioPreviewTextureToken", token);
        QObject * next = gp_ocio_preview::make_texture(window.contentItem(), effect, token);
        require(next != nullptr, "Native OCIO resource binding failed: " + effect->property("ocioPreviewError").toString().toStdString());
        effect->setProperty("ocioLutTexture", QVariant::fromValue(next));
        effect->setProperty("fragmentShader", QUrl(source));
        if (lut) gp_ocio_preview::retire_texture(lut);
        lut = next;
        gp_ocio_preview::release_assets(token); // Mirrors PreparedPreview RAII after claim.
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
        QCoreApplication::processEvents(); // Executes queued public cache purge after binding.
    }
    std::vector<float> render() {
        control.polishItems(); control.beginFrame(); control.sync(); control.render();
        QRhiReadbackResult readback;
        bool done = false;
        readback.completed = [&] { done = true; };
        auto updates = control.rhi()->nextResourceUpdateBatch();
        updates->readBackTexture(QRhiReadbackDescription(target.get()), &readback);
        control.commandBuffer()->resourceUpdate(updates);
        control.endFrame(); control.rhi()->finish();
        QCoreApplication::processEvents();
        require(done, "Native readback did not complete");
        require(readback.data.size() == qsizetype(size.width() * 4 * sizeof(float)), "Invalid float32 readback length");
        require(effect->property("ocioPreviewError").toString().isEmpty(), effect->property("ocioPreviewError").toString().toStdString());
        require(effect->property("status").toInt() != 2, "ShaderEffect reported error: " + effect->property("log").toString().toStdString());
        std::vector<float> pixels(size_t(size.width()) * 4);
        std::memcpy(pixels.data(), readback.data.constData(), size_t(readback.data.size()));
        return pixels;
    }
};
struct Processor {
    void * handle;
    Processor(const std::array<double, 8> & settings, const QString & path) {
        char error[4096] = {};
        const QByteArray utf8 = path.toUtf8();
        handle = gp_ocio_create_with_lut(settings.data(), path.isEmpty() ? nullptr : utf8.constData(), error, sizeof(error));
        require(handle != nullptr, error);
    }
    ~Processor() { gp_ocio_destroy(handle); }
    QJsonObject prepare(const QString & wrapper) {
        char error[4096] = {}; std::vector<char> text(256 * 1024);
        const size_t length = gp_ocio_shader(handle, text.data(), text.size(), error, sizeof(error));
        require(length != 0, error);
        uint32_t edge = 0;
        const size_t count = gp_ocio_texture3d(handle, nullptr, 0, &edge, error, sizeof(error));
        require(error[0] == 0, error);
        std::vector<float> values(count);
        if (count) require(gp_ocio_texture3d(handle, values.data(), count, &edge, error, sizeof(error)) == count, error);
        QString source = wrapper;
        source.replace("// GP_OCIO_GRADE", QString::fromUtf8(text.data(), qsizetype(length)));
        QFile generated(QString::fromLocal8Bit(qgetenv("GP_OCIO_NATIVE_LAST_SHADER")));
        if (generated.open(QIODevice::WriteOnly)) generated.write(source.toUtf8());
        const auto result = QJsonDocument::fromJson(gp_ocio_preview::prepare_assets(source, int(edge), values.data(), count).toUtf8()).object();
        require(!result.contains("error"), result.value("error").toString().toStdString());
        return result;
    }
    std::vector<float> expected(const std::vector<float> & pixels) {
        const size_t n = pixels.size() / 4;
        std::vector<float> r(n), g(n), b(n), out(pixels.size());
        for (size_t i = 0; i < n; ++i) { r[i] = pixels[i * 4]; g[i] = pixels[i * 4 + 1]; b[i] = pixels[i * 4 + 2]; }
        char error[4096] = {};
        require(gp_ocio_apply(handle, r.data(), g.data(), b.data(), uint32_t(n), 1, n * 4, n * 4, n * 4, error, sizeof(error)) == 1, error);
        for (size_t i = 0; i < n; ++i) { out[i * 4] = r[i]; out[i * 4 + 1] = g[i]; out[i * 4 + 2] = b[i]; out[i * 4 + 3] = 1; }
        return out;
    }
};
static QString cube(const QTemporaryDir & directory, const QString & name, int edge, int mode) {
    const QString path = directory.filePath(name + ".cube");
    QFile file(path); require(file.open(QIODevice::WriteOnly), "Cannot write fixture cube");
    QTextStream stream(&file); stream.setRealNumberPrecision(10);
    stream << "LUT_3D_SIZE " << edge << "\n";
    for (int b = 0; b < edge; ++b) for (int g = 0; g < edge; ++g) for (int r = 0; r < edge; ++r) {
        float x = float(r) / float(edge - 1), y = float(g) / float(edge - 1), z = float(b) / float(edge - 1);
        if (mode == 1) { x = 1 - x; y = 1 - y; z = 1 - z; }
        else if (mode == 2) { x = .1f + .8f * x * x; y = std::pow(y, .7f); z = 2 * z - .2f; }
        stream << x << " " << y << " " << z << "\n";
    }
    return path;
}
static double compare(const std::vector<float> & actual, const std::vector<float> & expected, const std::string & name) {
    double maximum = 0; size_t worst = 0;
    for (size_t i = 0; i < actual.size(); ++i) {
        require(std::isfinite(actual[i]), name + " produced non-finite GPU output");
        const double difference = std::abs(double(actual[i]) - expected[i]);
        if (difference > maximum) { maximum = difference; worst = i; }
    }
    std::cout << name << " max_abs_error=" << maximum << " worst_index=" << worst << " actual=" << actual[worst] << " expected=" << expected[worst] << "\n";
    require(maximum < .00001, name + " CPU/GPU difference exceeds 0.00001");
    return maximum;
}
int main(int argc, char ** argv) {
    try {
        const bool softwareCheck = argc > 1 && std::string(argv[1]) == "--software-check";
        const bool exceptionCheck = argc > 1 && std::string(argv[1]) == "--exception-check";
        QQuickWindow::setGraphicsApi(softwareCheck ? QSGRendererInterface::Software : expectedGraphicsApi);
        QGuiApplication application(argc, argv);
        if (exceptionCheck) {
            // This failure occurs inside shader_pack's QMutexLocker scope.
            // The following valid request must acquire the same mutex again.
            // CTest bounds this process so broken unwinding fails as a timeout.
            const auto failed = QJsonDocument::fromJson(gp_ocio_preview::bake(
                QStringLiteral("#version 440\n#error GP_OCIO_EXCEPTION_TEST\n")).toUtf8()).object();
            require(failed["error"].toString().contains("OCIO preview shader compilation failed"),
                "Invalid shader did not exercise the compilation exception");
            const QString source = QStringLiteral("#version 440\nlayout(location=0)out vec4 fragColor;void main(){fragColor=vec4(1);}");
            const auto recovered = QJsonDocument::fromJson(gp_ocio_preview::prepare_assets(source, 0, nullptr, 0).toUtf8()).object();
            require(!recovered.contains("error"), recovered["error"].toString().toStdString());
            const QString token = recovered["texture_token"].toString();
            require(!token.isEmpty() && QFile::exists(QUrl(recovered["source"].toString()).toLocalFile()),
                "Valid shader did not recover after the compilation exception");
            gp_ocio_preview::release_assets(token);
            require(gp_ocio_preview::pending().values.isEmpty(), "Recovery request leaked pending assets");
            std::cout << "shader_exception_lock_recovery=passed\n";
            return 0;
        }
        if (softwareCheck) {
            QQuickWindow window;
            QObject target;
            const QString source = "#version 440\nlayout(location=0)out vec4 fragColor;void main(){fragColor=vec4(1);}";
            const auto prepared = QJsonDocument::fromJson(gp_ocio_preview::prepare_assets(source, 0, nullptr, 0).toUtf8()).object();
            require(!prepared.contains("error"), prepared["error"].toString().toStdString());
            require(gp_ocio_preview::make_texture(window.contentItem(), &target, prepared["texture_token"].toString()) == nullptr, "Software renderer was accepted");
            require(target.property("ocioPreviewError").toString().contains("hardware graphics renderer"), "Software renderer error was not visible");
            gp_ocio_preview::release_assets(prepared["texture_token"].toString());
            require(gp_ocio_preview::pending().values.isEmpty(), "Rejected software token leaked");
            std::cout << "software_backend_rejection=passed\n";
            return 0;
        }
        require(argc >= 2, "Pass repository root, optionally official O4 cube path");
        QFile wrapperFile(QString::fromLocal8Bit(argv[1]) + "/src/qt_gpu/ocio_preview.frag");
        require(wrapperFile.open(QIODevice::ReadOnly), "Cannot read production shader wrapper");
        const QString wrapper = QString::fromUtf8(wrapperFile.readAll());
        QTemporaryDir directory; require(directory.isValid(), "Cannot create fixture directory");
        const QString identity = cube(directory, "identity", 2, 0), invert = cube(directory, "invert", 2, 1), nonlinear = cube(directory, "nonlinear", 5, 2);
        std::vector<float> input;
        for (int i = 0; i <= 256; ++i) {
            const float v = float(i) / 256;
            for (const auto & color : {std::array<float, 3>{v, v, v}, {v, 0, 1}, {1, v, 0}, {0, 1, v}})
                input.insert(input.end(), {color[0], color[1], color[2], 1});
        }
        for (const auto & color : {std::array<float, 3>{-.25f, .5f, 1.25f}, {1.25f, -.25f, .5f}, {.5f, 1.25f, -.25f}, {-.001f, 0, 1.001f}})
            input.insert(input.end(), {color[0], color[1], color[2], 1});
        NativeFixture fixture(input);
        const std::array<double, 8> neutral{}, grade{.1, .15, .2, -.2, .35, .2, -.1, .1};
        QJsonArray results;
        const auto run = [&](const QString & name, const QString & path, const std::array<double, 8> & parameters) {
            Processor processor(parameters, path);
            const auto resources = processor.prepare(wrapper);
            fixture.bind(resources["source"].toString(), resources["texture_token"].toString());
            const double error = compare(fixture.render(), processor.expected(input), name.toStdString());
            results.append(QJsonObject{{"case", name}, {"max_abs_error", error}});
        };
        run("neutral", "", neutral); run("grade_only", "", grade);
        run("identity_lut", identity, neutral); run("invert_lut", invert, neutral);
        run("invert_lut_grade", invert, grade); run("nonlinear_lut", nonlinear, neutral);
        run("nonlinear_lut_grade", nonlinear, grade);
        if (argc >= 3 && argv[2][0]) { run("o4_lut", QString::fromLocal8Bit(argv[2]), neutral); run("o4_lut_grade", QString::fromLocal8Bit(argv[2]), grade); }
        // Distinct official processors exercise swaps and the production public
        // cache purge. Read back every result, including the first after purge.
        for (int i = 0; i < 70; ++i) {
            auto varying = grade; varying[4] = -.8 + i * .02;
            run("cache_swap_" + QString::number(i), nonlinear, varying);
        }
        require(gp_ocio_preview::cache().packs.size() <= 64, "Shader file cache exceeded 64 entries");
        require(gp_ocio_preview::pending().values.isEmpty(), "Unclaimed assets leaked after successful claims");
        require(gp_ocio_preview::accepted_shaders().value(&fixture.window).sources.size() < 64, "Public cache purge did not execute");
        auto lastSettings = grade; lastSettings[4] = -.8 + 69 * .02;
        Processor lastProcessor(lastSettings, nonlinear);
        fixture.window.releaseResources(); fixture.window.update();
        QCoreApplication::processEvents();
        results.append(QJsonObject{{"case", "same_binding_after_public_release"},
            {"max_abs_error", compare(fixture.render(), lastProcessor.expected(input), "same_binding_after_public_release")}});
        fixture.recreate();
        results.append(QJsonObject{{"case", "same_binding_after_scenegraph_recreation"},
            {"max_abs_error", compare(fixture.render(), lastProcessor.expected(input), "same_binding_after_scenegraph_recreation")}});
        run("after_explicit_release", nonlinear, grade);
        // Stale/failed result disposal and invalid dimensions are bounded.
        Processor stale(grade, invert); const auto discarded = stale.prepare(wrapper);
        gp_ocio_preview::release_assets(discarded["texture_token"].toString());
        require(gp_ocio_preview::pending().values.isEmpty(), "Discarded assets leaked");
        QString validWrapper = wrapper;
        validWrapper.replace("// GP_OCIO_GRADE", "vec4 applyOcioGrade(vec4 value) { return value; }");
        const auto invalid = QJsonDocument::fromJson(gp_ocio_preview::prepare_assets(validWrapper, 129, nullptr, 0).toUtf8()).object();
        require(invalid["error"].toString().contains("dimensions"), "Invalid texture dimensions were accepted or failed for the wrong reason");
        // Evict a live pack, then reacquire it: its exact owner and file persist.
        const QString pinnedCode = validWrapper + "\n// pinned regression";
        auto pinned = gp_ocio_preview::shader_pack(pinnedCode);
        const QString pinnedPath = pinned->path;
        const QString pinnedKey = QString::fromLatin1(QCryptographicHash::hash(pinnedCode.toUtf8(), QCryptographicHash::Sha256).toHex());
        { auto & cache = gp_ocio_preview::cache(); QMutexLocker lock(&cache.mutex); cache.packs.remove(pinnedKey); cache.recent.removeAll(pinnedKey); }
        auto reused = gp_ocio_preview::shader_pack(pinnedCode);
        require(pinned == reused && QFile::exists(pinnedPath), "Evicted leased shader owner was not reused");
        { auto & cache = gp_ocio_preview::cache(); QMutexLocker lock(&cache.mutex); cache.packs.remove(pinnedKey); cache.recent.removeAll(pinnedKey); }
        reused.reset();
        std::weak_ptr<gp_ocio_preview::ShaderPack> oldWeak = pinned;
        std::thread retired([old = std::move(pinned)]() mutable { old.reset(); });
        while (!oldWeak.expired()) std::this_thread::yield();
        auto regenerated = gp_ocio_preview::shader_pack(pinnedCode);
        retired.join();
        require(regenerated->path != pinnedPath && QFile::exists(regenerated->path), "New shader generation shared a retired file path");
        // Render-resource errors cross to GUI only for the current token.
        QObject errorTarget; errorTarget.setProperty("ocioPreviewTextureToken", "current");
        gp_ocio_preview::ErrorTarget{QPointer<QObject>(&errorTarget), "stale"}.report("stale error");
        QCoreApplication::processEvents();
        require(errorTarget.property("ocioPreviewError").toString().isEmpty(), "Stale native error altered current preview");
        gp_ocio_preview::ErrorTarget{QPointer<QObject>(&errorTarget), "current"}.report("visible error");
        QCoreApplication::processEvents();
        require(errorTarget.property("ocioPreviewError").toString() == "visible error", "Current native error was lost");
        std::cout << "cache_purge=passed stale_disposal=passed generation_ownership=passed error_tokens=passed cases=" << results.size() << "\n";
        if (argc >= 4) { QFile output(QString::fromLocal8Bit(argv[3])); require(output.open(QIODevice::WriteOnly), "Cannot write result JSON"); output.write(QJsonDocument(QJsonObject{{"backend", backendName}, {"cases", results}, {"cache_purge", true}, {"stale_disposal", true}, {"generation_ownership", true}, {"error_tokens", true}}).toJson()); }
        return 0;
    } catch (const std::exception & error) { std::cerr << "FAIL: " << error.what() << "\n"; return 1; }
}
