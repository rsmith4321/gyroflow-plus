// SPDX-License-Identifier: GPL-3.0-or-later
// Qt resource adapter only. Shader generation and LUT evaluation belong to OCIO.
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QFile>
#include <QHash>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMutex>
#include <QMutexLocker>
#include <QPointer>
#include <QQmlEngine>
#include <QQuickItem>
#include <QQuickWindow>
#include <QRunnable>
#include <QSaveFile>
#include <QSet>
#include <QSGTexture>
#include <QSGTextureProvider>
#include <QSGRendererInterface>
#include <QTemporaryDir>
#include <QUrl>
#include <QUuid>
#if QT_VERSION >= QT_VERSION_CHECK(6, 6, 0)
# include <rhi/qrhi.h>
# include <rhi/qshaderbaker.h>
#else
# include <private/qrhi_p.h>
# include <private/qshaderbaker_p.h>
#endif
#include <cmath>
#include <exception>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <vector>

namespace gp_ocio_preview {
struct ShaderPack {
    QString path;
    ~ShaderPack() { QFile::remove(path); }
};
struct ShaderCache {
    QTemporaryDir directory;
    QMutex mutex;
    QHash<QString, std::shared_ptr<ShaderPack>> packs;
    QHash<QString, std::weak_ptr<ShaderPack>> leased;
    QList<QString> recent;
};
static ShaderCache & cache() { static ShaderCache value; return value; }

// 64 recent packs, plus packs owned by live/pending previews. Pruning never
// removes a shader needed by a live preview after scenegraph recreation.
static std::shared_ptr<ShaderPack> shader_pack(const QString & source) {
    if (source.isEmpty() || source.size() > 1024 * 1024)
        throw std::runtime_error("Invalid generated preview shader size.");
    ShaderCache & c = cache();
    const QMutexLocker lock(&c.mutex);
    if (!c.directory.isValid())
        throw std::runtime_error("Cannot create the generated preview shader cache.");
    const QByteArray code = source.toUtf8();
    const QString key = QString::fromLatin1(QCryptographicHash::hash(code, QCryptographicHash::Sha256).toHex());
    // A live/pending preview may still pin a pack evicted from the recent list.
    // Reuse its owner: two owners with the same path would unlink each other's
    // file on destruction when a user returns to an older slider value.
    for (auto it = c.leased.begin(); it != c.leased.end();) {
        if (it.value().expired()) it = c.leased.erase(it); else ++it;
    }
    auto pack = c.packs.value(key);
    if (!pack) pack = c.leased.value(key).lock();
    if (!pack) {
        QShaderBaker baker;
        baker.setSourceString(code, QShader::FragmentStage, QStringLiteral("ocio_preview.frag"));
        baker.setGeneratedShaders({
            {QShader::SpirvShader, QShaderVersion(100)},
            {QShader::GlslShader, QShaderVersion(300, QShaderVersion::GlslEs)},
            {QShader::GlslShader, QShaderVersion(330)},
            {QShader::HlslShader, QShaderVersion(50)},
            {QShader::MslShader, QShaderVersion(12)}
        });
        baker.setGeneratedShaderVariants({QShader::StandardShader});
        const QShader shader = baker.bake();
        if (!shader.isValid())
            throw std::runtime_error((QStringLiteral("OCIO preview shader compilation failed: ") + baker.errorMessage()).toStdString());
        const QByteArray bytes = shader.serialized();
        // A retired pack's final deletion may run on the render thread after
        // its weak owner expires. Give each new owner a unique path so that
        // deletion can never unlink a regenerated pack with the same code.
        const QString path = c.directory.path() + QLatin1Char('/') + key + QLatin1Char('-')
            + QUuid::createUuid().toString(QUuid::WithoutBraces) + QStringLiteral(".qsb");
        QSaveFile file(path);
        if (bytes.isEmpty() || !file.open(QIODevice::WriteOnly)
            || file.write(bytes) != bytes.size() || !file.commit())
            throw std::runtime_error("Cannot write the generated preview shader.");
        pack = std::make_shared<ShaderPack>();
        pack->path = path;
    }
    c.packs.insert(key, pack);
    c.leased.insert(key, pack);
    c.recent.removeAll(key);
    c.recent.append(key);
    while (c.recent.size() > 64) c.packs.remove(c.recent.takeFirst());
    return pack;
}
struct Assets {
    std::shared_ptr<ShaderPack> shader;
    int edge = 0;
    std::vector<float> rgba;
};
struct PendingAssets {
    QMutex mutex;
    QHash<QString, std::shared_ptr<const Assets>> values;
};
static PendingAssets & pending() { static PendingAssets value; return value; }
static QString error_json(const char * error) {
    return QString::fromUtf8(QJsonDocument(QJsonObject{{QStringLiteral("error"), QString::fromUtf8(error)}}).toJson(QJsonDocument::Compact));
}

// The worker owns this token until the synchronous GUI signal claims it.
// Rust RAII releases every unclaimed/stale result, including controller removal.
static QString prepare_assets(const QString & source, int edge, const float * rgb, size_t count) noexcept {
    try {
        auto data = std::make_shared<Assets>();
        data->shader = shader_pack(source);
        if (edge != 0) {
            if (edge < 2 || edge > 128 || !rgb || count != size_t(edge) * edge * edge * 3)
                throw std::runtime_error("Invalid OCIO preview texture dimensions.");
            data->edge = edge;
            data->rgba.resize(count / 3 * 4);
            // Storage conversion only: preserve OCIO's RGB values and array order.
            for (size_t i = 0; i < count / 3; ++i) {
                for (size_t channel = 0; channel < 3; ++channel) {
                    if (!std::isfinite(rgb[i * 3 + channel]))
                        throw std::runtime_error("Invalid OCIO preview texture value.");
                    data->rgba[i * 4 + channel] = rgb[i * 3 + channel];
                }
                data->rgba[i * 4 + 3] = 1.0f;
            }
        } else if (count != 0) throw std::runtime_error("Unexpected OCIO preview texture data.");
        const QString token = QUuid::createUuid().toString(QUuid::WithoutBraces);
        PendingAssets & p = pending();
        { const QMutexLocker lock(&p.mutex); p.values.insert(token, data); }
        return QString::fromUtf8(QJsonDocument(QJsonObject{
            {QStringLiteral("source"), QUrl::fromLocalFile(data->shader->path).toString()},
            {QStringLiteral("texture_token"), token}
        }).toJson(QJsonDocument::Compact));
    } catch (const std::exception & e) { return error_json(e.what()); }
    catch (...) { return error_json("OCIO preview preparation failed."); }
}
static void release_assets(const QString & token) {
    PendingAssets & p = pending();
    const QMutexLocker lock(&p.mutex);
    p.values.remove(token);
}
// Standalone shader acceptance harness entry point.
static QString bake(const QString & source) noexcept {
    try {
        auto pack = shader_pack(source);
        return QString::fromUtf8(QJsonDocument(QJsonObject{{QStringLiteral("source"), QUrl::fromLocalFile(pack->path).toString()}}).toJson(QJsonDocument::Compact));
    } catch (const std::exception & e) { return error_json(e.what()); }
    catch (...) { return error_json("OCIO preview shader preparation failed."); }
}
struct ErrorTarget {
    QPointer<QObject> object;
    QString token;
    void report(const QString & message) const {
        const ErrorTarget target = *this;
        // Only the queued GUI callback dereferences the guarded QML object.
        QMetaObject::invokeMethod(QCoreApplication::instance(), [target, message] {
            if (target.object && target.object->property("ocioPreviewTextureToken").toString() == target.token)
                target.object->setProperty("ocioPreviewError", message);
        }, Qt::QueuedConnection);
    }
};
class DataTexture final : public QSGTexture {
    std::shared_ptr<const Assets> m_assets;
    ErrorTarget m_error;
    std::unique_ptr<QRhiTexture> m_texture;
    bool m_failed = false;
public:
    DataTexture(std::shared_ptr<const Assets> assets, ErrorTarget error) : m_assets(std::move(assets)), m_error(std::move(error)) {
        setFiltering(Nearest); setMipmapFiltering(None);
        setHorizontalWrapMode(ClampToEdge); setVerticalWrapMode(ClampToEdge);
        // Qt's sampler W defaults to Repeat. The official processor contains a
        // 0..1 RangeTransform before the LUT, so no weighted sample wraps in W.
    }
    qint64 comparisonKey() const override { return qint64(reinterpret_cast<quintptr>(this)); }
    QRhiTexture * rhiTexture() const override { return m_texture.get(); }
    QSize textureSize() const override { return QSize(m_assets->edge, m_assets->edge); }
    bool hasAlphaChannel() const override { return false; }
    bool hasMipmaps() const override { return false; }
    bool isAtlasTexture() const override { return false; }
    void commitTextureOperations(QRhi * rhi, QRhiResourceUpdateBatch * updates) override {
        if (m_texture || m_failed) return;
        const auto fail = [this](const QString & message) { m_failed = true; m_texture.reset(); m_error.report(message); };
        if (!rhi || !updates || !rhi->isFeatureSupported(QRhi::ThreeDimensionalTextures)
            || !rhi->isTextureFormatSupported(QRhiTexture::RGBA32F, QRhiTexture::ThreeDimensional)) {
            fail(QStringLiteral("This graphics device cannot display the OCIO float 3D LUT.")); return;
        }
        const int edge = m_assets->edge;
        m_texture.reset(rhi->newTexture(QRhiTexture::RGBA32F, edge, edge, edge, 1, QRhiTexture::ThreeDimensional));
        if (!m_texture || !m_texture->create()) { fail(QStringLiteral("Could not create the OCIO preview 3D LUT texture.")); return; }
        const size_t sliceFloats = size_t(edge) * edge * 4;
        std::vector<QRhiTextureUploadEntry> entries;
        entries.reserve(size_t(edge));
        for (int z = 0; z < edge; ++z) {
            QRhiTextureSubresourceUploadDescription description(m_assets->rgba.data() + size_t(z) * sliceFloats, quint32(sliceFloats * sizeof(float)));
            description.setDataStride(quint32(edge * 4 * sizeof(float)));
            description.setSourceSize(QSize(edge, edge));
            entries.emplace_back(z, 0, description);
        }
        QRhiTextureUploadDescription description;
        description.setEntries(entries.begin(), entries.end());
        updates->uploadTexture(m_texture.get(), description);
    }
};
class TextureProvider final : public QSGTextureProvider {
    std::unique_ptr<DataTexture> m_texture;
public:
    TextureProvider(std::shared_ptr<const Assets> assets, ErrorTarget error) : m_texture(new DataTexture(std::move(assets), std::move(error))) {}
    QSGTexture * texture() const override { return m_texture.get(); }
};
struct RenderState {
    std::mutex mutex;
    TextureProvider * provider = nullptr; // Render-thread ownership only.
    QMetaObject::Connection invalidation;
    void clear(bool final = false) {
        const std::lock_guard<std::mutex> lock(mutex);
        delete provider; provider = nullptr;
        if (final) QObject::disconnect(invalidation);
    }
};
class CleanupJob final : public QRunnable {
    std::shared_ptr<RenderState> m_state;
    bool m_final;
public:
    CleanupJob(std::shared_ptr<RenderState> state, bool final) : m_state(std::move(state)), m_final(final) {}
    void run() override { m_state->clear(m_final); }
};
class TextureItem final : public QQuickItem {
    std::shared_ptr<const Assets> m_assets;
    ErrorTarget m_error;
    std::shared_ptr<RenderState> m_state;
    QPointer<QQuickWindow> m_window;
    void retire(bool final = true) {
        if (m_state && m_window) m_window->scheduleRenderJob(new CleanupJob(m_state, final), QQuickWindow::BeforeSynchronizingStage);
    }
    void setWindow(QQuickWindow * window) {
        retire();
        // Retain old invalidation until its cleanup job executes: this handles
        // a window closing without another render frame.
        m_window = window;
        m_state = std::make_shared<RenderState>();
        if (window) {
            const auto state = m_state;
            m_state->invalidation = QObject::connect(window, &QQuickWindow::sceneGraphInvalidated,
                window, [state] { state->clear(); }, Qt::DirectConnection);
        }
    }
public:
    TextureItem(QQuickItem * parent, std::shared_ptr<const Assets> assets, ErrorTarget error)
        : QQuickItem(parent), m_assets(std::move(assets)), m_error(std::move(error)) {
        setWindow(window());
        QObject::connect(this, &QQuickItem::windowChanged, this, [this](QQuickWindow * window) { setWindow(window); });
        QQmlEngine::setObjectOwnership(this, QQmlEngine::CppOwnership);
    }
    ~TextureItem() override {
        // QQuickItem's base destructor emits windowChanged after our members
        // have been destroyed. Stop the self callback before that teardown.
        QObject::disconnect(this, nullptr, this, nullptr);
        retire();
    }
    bool isTextureProvider() const override { return m_assets->edge != 0; }
    QSGTextureProvider * textureProvider() const override {
        if (!isTextureProvider() || !m_state) return nullptr;
        const std::lock_guard<std::mutex> lock(m_state->mutex);
        if (!m_state->provider) m_state->provider = new TextureProvider(m_assets, m_error);
        return m_state->provider;
    }
    void releaseResources() override { retire(false); }
};
// GUI-only inventory also makes retirement safe if QML passes a stale object.
static QSet<QObject *> & owned_items() { static QSet<QObject *> value; return value; }
struct AcceptedShaders { QSet<QString> sources; bool purgeQueued = false; };
static QHash<QQuickWindow *, AcceptedShaders> & accepted_shaders() {
    static QHash<QQuickWindow *, AcceptedShaders> value; return value;
}
static void accept_shader(QQuickWindow * window, const QString & path) {
    auto & accepted = accepted_shaders();
    if (!accepted.contains(window)) {
        QObject::connect(window, &QObject::destroyed, [window] { accepted_shaders().remove(window); });
    }
    auto & state = accepted[window];
    state.sources.insert(path);
    if (state.sources.size() < 64 || state.purgeQueued) return;
    state.purgeQueued = true;
    const QPointer<QQuickWindow> guarded(window);
    // ShaderEffect keeps full QShader packs in a GUI URL cache. This public
    // method purges it (Qt 6.7.3/6.11.2); deleting our files alone does not.
    // Queue after QML has synchronously bound the new resource and shader.
    QMetaObject::invokeMethod(window, [guarded] {
        if (!guarded) return;
        auto & state = accepted_shaders()[guarded];
        state.sources.clear(); state.purgeQueued = false;
        guarded->releaseResources();
        guarded->update();
    }, Qt::QueuedConnection);
}
static QObject * make_texture(QQuickItem * parent, QObject * errorTarget, const QString & token) {
    if (!parent || !errorTarget) return nullptr;
    auto window = parent->window();
    if (!window || window->rendererInterface()->graphicsApi() == QSGRendererInterface::Software) {
        errorTarget->setProperty("ocioPreviewError", QStringLiteral("OCIO color preview requires a hardware graphics renderer. The software renderer cannot display these adjustments."));
        return nullptr;
    }
    std::shared_ptr<const Assets> assets;
    { PendingAssets & p = pending(); const QMutexLocker lock(&p.mutex); assets = p.values.take(token); }
    if (!assets) return nullptr;
    accept_shader(window, assets->shader->path);
    auto item = new TextureItem(parent, std::move(assets), ErrorTarget{QPointer<QObject>(errorTarget), token});
    owned_items().insert(item);
    QObject::connect(item, &QObject::destroyed, [](QObject * object) { owned_items().remove(object); });
    return item;
}
static void retire_texture(QObject * item) { if (owned_items().contains(item)) item->deleteLater(); }
}
