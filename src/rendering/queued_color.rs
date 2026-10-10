// SPDX-License-Identifier: GPL-3.0-or-later
//! Export colour of a queued job whose settings live in a project file.
//!
//! A saved render queue refers to such a job by its project file, and that
//! file is saved again whenever the project is queued or saved with another
//! grade. The queue therefore also keeps the job's own LUT and eight controls
//! and lays them over the project's `output` when it is restored. Nothing
//! else in `output` is touched.

use serde_json::{Map, Value};

pub const FIELDS: [&str; 9] = ["lut_url", "brightness", "contrast", "shadows", "highlights", "exposure", "saturation", "warmth", "tint"];

/// The colour fields of a job's serialized `RenderOptions`. Neutral values
/// ("" and 0) are kept, so they also win over the project on restore.
/// `create_bookmark` is asked only for a non-empty LUT URL (macOS keeps a
/// security-scoped bookmark next to it, as project files do).
pub fn snapshot(output: &Value, create_bookmark: impl Fn(&str) -> Option<String>) -> Option<Value> {
    let output = output.as_object()?;
    let mut color = Map::new();
    if let Some(url) = output.get("lut_url").and_then(Value::as_str) {
        color.insert("lut_url".into(), url.into());
        if let Some(bookmark) = Some(url).filter(|x| !x.is_empty()).and_then(create_bookmark).filter(|x| !x.is_empty()) {
            color.insert("lut_bookmark".into(), bookmark.into());
        }
    }
    for key in &FIELDS[1..] {
        if let Some(v) = output.get(*key).filter(|x| x.as_f64().is_some()) {
            color.insert((*key).into(), v.clone());
        }
    }
    (!color.is_empty()).then_some(Value::Object(color))
}

/// The project's `output` with the queued colour fields laid over it, field
/// by field. Without saved colour (queues saved by older versions) or for a
/// non-object `output` the project's value is returned unchanged; a field
/// missing from the saved colour, or of another type, keeps the project's
/// value. A LUT bookmark is resolved as `core::import_gyroflow_data` resolves
/// a project's: only next to a non-empty URL, and only a non-empty result
/// replaces it.
pub fn restore(project_output: &Value, color: Option<&Value>, resolve_bookmark: impl Fn(&str) -> Option<String>) -> Value {
    let mut output = project_output.clone();
    let (Some(out), Some(color)) = (output.as_object_mut(), color.and_then(Value::as_object)) else { return output; };
    if let Some(url) = color.get("lut_url").and_then(Value::as_str) {
        let resolved = color.get("lut_bookmark").and_then(Value::as_str)
            .filter(|x| !x.is_empty() && !url.is_empty())
            .and_then(resolve_bookmark)
            .filter(|x| !x.is_empty());
        out.insert("lut_url".into(), resolved.unwrap_or_else(|| url.to_owned()).into());
    }
    for key in &FIELDS[1..] {
        if let Some(v) = color.get(*key).filter(|x| x.as_f64().is_some()) {
            out.insert((*key).into(), v.clone());
        }
    }
    output
}

/// An imported project with `color` laid over its `output` by `restore`.
/// Without colour, or without an object `output`, it is returned unchanged.
pub fn restore_project(mut project: Value, color: Option<&Value>, resolve_bookmark: impl Fn(&str) -> Option<String>) -> Value {
    if let (Some(color), Some(output)) = (color, project.get_mut("output").filter(|x| x.is_object())) {
        *output = restore(output, Some(color), resolve_bookmark);
    }
    project
}
