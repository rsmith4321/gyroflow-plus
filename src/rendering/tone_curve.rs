// SPDX-License-Identifier: GPL-3.0-or-later
//! Bounded, display-referred OCIO video-tone prototype. Samples and provenance
//! are reproducible with tests/export-lut/generate_tone_tables.py (OCIO 2.4.2).
//! No implicit color-space conversion; inputs outside [0,1] are clipped.

pub const SAMPLES: usize = 4097;
const PARAMETERS: usize = 101;
const TABLE: &[u8; 2 * PARAMETERS * SAMPLES * 4] =
    include_bytes!("../../resources/color/ocio-video-tone-v1.bin");

pub struct ToneCurve {
    values: Vec<f32>,
}

fn entry(kind: usize, parameter: usize, sample: usize) -> f32 {
    let offset = ((kind * PARAMETERS + parameter) * SAMPLES + sample) * 4;
    f32::from_le_bytes(TABLE[offset..offset + 4].try_into().unwrap())
}

fn parameter_curve(kind: usize, amount: f64) -> Vec<f32> {
    let position = (amount * 100.0 + 50.0).clamp(0.0, 100.0);
    let lo = position.floor() as usize;
    let hi = (lo + 1).min(PARAMETERS - 1);
    let fraction = (position - lo as f64) as f32;
    (0..SAMPLES).map(|i| {
        let a = entry(kind, lo, i);
        a + fraction * (entry(kind, hi, i) - a)
    }).collect()
}

fn lookup(values: &[f32], input: f32) -> f32 {
    let position = input.clamp(0.0, 1.0) * (SAMPLES - 1) as f32;
    let lo = (position as usize).min(SAMPLES - 1);
    let hi = (lo + 1).min(SAMPLES - 1);
    let a = values[lo];
    a + (position - lo as f32) * (values[hi] - a)
}

impl ToneCurve {
    pub fn new(shadows: f64, highlights: f64) -> Result<Option<Self>, String> {
        if [shadows, highlights].iter().any(|v| !v.is_finite() || v.abs() > 0.5) {
            return Err("Shadows and highlights must be between −50% and +50%.".into());
        }
        if shadows == 0.0 && highlights == 0.0 { return Ok(None); }
        let highlights = parameter_curve(0, highlights);
        let shadows = parameter_curve(1, shadows);
        let values = highlights.into_iter().map(|v| lookup(&shadows, v)).collect();
        Ok(Some(Self { values }))
    }

    #[inline]
    pub fn apply(&self, input: f32) -> f32 { lookup(&self.values, input) }

    // Pack IEEE float bytes in two RGB8 texels; RGBA8 would be premultiplied
    // by Qt's image upload and corrupt the encoded float's low bytes.
    // The preview uses texelFetch and manual interpolation, just like export.
    pub fn texture_bytes(&self) -> Vec<u8> {
        let mut bytes = vec![0; 256 * 33 * 3];
        for (i, value) in self.values.iter().enumerate() {
            let value = value.to_le_bytes();
            bytes[i * 6..i * 6 + 4].copy_from_slice(&value);
        }
        bytes
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn neutral_is_bypassed_and_invalid_controls_rejected() {
        assert!(ToneCurve::new(0.0, 0.0).unwrap().is_none());
        for invalid in [f64::NAN, f64::INFINITY, -0.501, 0.501] {
            assert!(ToneCurve::new(invalid, 0.0).is_err());
            assert!(ToneCurve::new(0.0, invalid).is_err());
        }
    }
    #[test]
    fn all_parameter_extremes_are_bounded_monotonic_and_preserve_endpoints() {
        for s in [-0.5, -0.217, 0.0, 0.319, 0.5] {
            for h in [-0.5, -0.217, 0.0, 0.319, 0.5] {
                if let Some(curve) = ToneCurve::new(s, h).unwrap() {
                    assert_eq!(curve.apply(-1.0), 0.0);
                    assert_eq!(curve.apply(2.0), 1.0);
                    let mut previous = 0.0;
                    for i in 0..=65536 {
                        let current = curve.apply(i as f32 / 65536.0);
                        assert!(current.is_finite() && current >= previous && current <= 1.0);
                        previous = current;
                    }
                    assert_eq!(curve.texture_bytes().len(), 256 * 33 * 3);
                }
            }
        }
    }
    #[test]
    fn tonal_controls_are_local_and_directional() {
        let shadows = ToneCurve::new(0.5, 0.0).unwrap().unwrap();
        let highlights = ToneCurve::new(0.0, -0.5).unwrap().unwrap();
        assert!(shadows.apply(0.1) > 0.1);
        assert_eq!(shadows.apply(0.75), 0.75);
        assert_eq!(highlights.apply(0.1), 0.1);
        assert!(highlights.apply(0.9) < 0.9);
    }
}
