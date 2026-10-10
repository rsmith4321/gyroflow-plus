// SPDX-License-Identifier: GPL-3.0-or-later
//! Experimental Qt resource plumbing. OCIO generates all color/LUT operations.
use cpp::cpp;
use qmetaobject::{QJSValue, QString, QVariant};
use crate::core::filesystem;
use crate::rendering::{cube_lut::CubeLut, ocio_runtime::{OcioProcessor, Settings}};
use std::io::Write;

cpp! {{
    #include "src/qt_gpu/ocio_preview.cpp"
}}

#[derive(Default)]
pub struct PreviewState {
    pub generation: u64,
    pub running: bool,
    pub pending: Option<(u64, i32, Settings, String)>,
}

// The GUI signal claims the token synchronously. Every discarded completion
// releases its immutable data, even if its controller was already destroyed.
struct AssetLease { token: String }
impl Drop for AssetLease {
    fn drop(&mut self) {
        let token = QString::from(self.token.as_str());
        cpp!(unsafe [token as "QString"] { gp_ocio_preview::release_assets(token); });
    }
}

pub struct PreparedPreview {
    pub source: String,
    pub active: bool,
    lease: AssetLease,
}
impl PreparedPreview {
    pub fn texture_token(&self) -> &str { &self.lease.token }
}

pub fn prepare(settings: Settings, lut_url: &str) -> Result<PreparedPreview, String> {
    // Reuse the supported bounded cube subset, but not its legacy atlas or LUT
    // evaluator. OCIO owns parsing/evaluation of the validated canonical file.
    let file = if !lut_url.is_empty() {
        let mut source = filesystem::open_file(lut_url, false, false).map_err(|e| e.to_string())?;
        let bytes = CubeLut::read_bounded(source.get_file())?;
        let cube = CubeLut::parse(&bytes)?;
        let mut file = tempfile::Builder::new().suffix(".cube").tempfile().map_err(|e| e.to_string())?;
        file.write_all(&cube.canonical_cube()).map_err(|e| e.to_string())?;
        file.flush().map_err(|e| e.to_string())?;
        Some(file)
    } else { None };
    let processor = OcioProcessor::with_lut(settings, file.as_ref().map(|f| f.path()))?;
    let resources = processor.gpu_resources()?;
    let source = QString::from(include_str!("ocio_preview.frag").replace("// GP_OCIO_GRADE", &resources.text));
    let (edge, pointer, count) = resources.texture.as_ref().map_or((0i32, std::ptr::null(), 0usize),
        |t| (t.edge as i32, t.values.as_ptr(), t.values.len()));
    let prepared = cpp!(unsafe [source as "QString", edge as "int", pointer as "const float *", count as "size_t"] -> QString as "QString" {
        return gp_ocio_preview::prepare_assets(source, edge, pointer, count);
    });
    let value: serde_json::Value = serde_json::from_str(&prepared.to_string()).map_err(|e| e.to_string())?;
    if let Some(error) = value.get("error").and_then(|x| x.as_str()) { return Err(error.to_owned()); }
    let token = value.get("texture_token").and_then(|x| x.as_str()).filter(|x| !x.is_empty())
        .ok_or("No prepared OCIO preview resources.")?.to_owned();
    let lease = AssetLease { token };
    let source = value.get("source").and_then(|x| x.as_str()).filter(|x| x.starts_with("file:"))
        .ok_or("No generated preview shader.")?.to_owned();
    Ok(PreparedPreview { source, active: processor.is_active(), lease })
}

pub fn create_texture(parent: QJSValue, error_target: QJSValue, token: QString) -> QVariant {
    cpp!(unsafe [parent as "QJSValue", error_target as "QJSValue", token as "QString"] -> QVariant as "QVariant" {
        QObject * item = gp_ocio_preview::make_texture(qobject_cast<QQuickItem *>(parent.toQObject()), error_target.toQObject(), token);
        return item ? QVariant::fromValue(item) : QVariant();
    })
}
pub fn retire_texture(item: QJSValue) {
    cpp!(unsafe [item as "QJSValue"] { gp_ocio_preview::retire_texture(item.toQObject()); });
}
