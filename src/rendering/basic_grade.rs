// SPDX-License-Identifier: GPL-3.0-or-later
//! Small display-referred grade. Exposure is in gamma-2.4 display-linear stops
//! after the user-selected viewing LUT, not camera/log-code exposure or RAW WB.
//! Per-channel exposure and video saturation are independently checked against
//! pinned OCIO 2.4.2 GradingPrimary. Only parameter preparation uses powf.

pub const LUMA: [f64; 3] = [0.2126, 0.7152, 0.0722];

#[derive(Clone, Copy, Default)]
pub struct BasicGradeSettings {
    pub exposure: f64,
    pub saturation: f64,
    pub warmth: f64,
    pub tint: f64,
}

pub struct BasicGrade {
    pub gains: [f64; 3],
    pub saturation: f64,
    active: bool,
}

impl BasicGrade {
    pub fn new(s: BasicGradeSettings) -> Result<Self, String> {
        if !s.exposure.is_finite() || s.exposure.abs() > 2.0 {
            return Err("Exposure must be between −2 and +2 display stops.".into());
        }
        if [s.saturation, s.warmth, s.tint]
            .iter()
            .any(|x| !x.is_finite() || x.abs() > 1.0)
        {
            return Err("Saturation, temperature and tint must be between −100% and +100%.".into());
        }
        let active = s.exposure != 0.0 || s.saturation != 0.0 || s.warmth != 0.0 || s.tint != 0.0;
        // Relative RGB balance in linear display light. Normalize the color
        // gains so neutral white's Rec.709 linear luminance remains unchanged.
        // This deliberately does not claim a calibrated Kelvin temperature.
        let stops = [
            0.75 * s.warmth + 0.25 * s.tint,
            -0.5 * s.tint,
            -0.75 * s.warmth + 0.25 * s.tint,
        ];
        let linear = stops.map(|v| v.exp2());
        let norm = linear.iter().zip(LUMA).map(|(v, w)| v * w).sum::<f64>();
        let exposure = s.exposure.exp2();
        let gains = linear.map(|v| (v / norm * exposure).powf(1.0 / 2.4));
        Ok(Self {
            gains,
            saturation: 1.0 + s.saturation,
            active,
        })
    }

    pub fn is_active(&self) -> bool {
        self.active
    }

    pub fn saturate(&self, rgb: [f32; 3]) -> [f32; 3] {
        let y = rgb
            .iter()
            .zip(LUMA)
            .map(|(v, w)| *v as f64 * w)
            .sum::<f64>();
        rgb.map(|v| (y + self.saturation * (v as f64 - y)).clamp(0.0, 1.0) as f32)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn neutral_and_parameter_validation() {
        let grade = BasicGrade::new(BasicGradeSettings::default()).unwrap();
        assert!(!grade.is_active());
        assert_eq!(grade.gains, [1.0; 3]);
        assert_eq!(grade.saturation, 1.0);
        for invalid in [f64::NAN, f64::INFINITY, -2.01, 2.01] {
            assert!(
                BasicGrade::new(BasicGradeSettings {
                    exposure: invalid,
                    ..Default::default()
                })
                .is_err()
            );
        }
        for invalid in [f64::NAN, f64::NEG_INFINITY, -1.01, 1.01] {
            for field in 0..3 {
                let mut s = BasicGradeSettings::default();
                match field {
                    0 => s.saturation = invalid,
                    1 => s.warmth = invalid,
                    _ => s.tint = invalid,
                }
                assert!(BasicGrade::new(s).is_err());
            }
        }
    }
    #[test]
    fn balance_preserves_linear_white_luminance_and_exposure_doubles_it() {
        for warmth in [-1.0, 0.0, 0.371, 1.0] {
            for tint in [-1.0, 0.0, 0.219, 1.0] {
                for exposure in [-2.0, 0.0, 1.0, 2.0] {
                    let g = BasicGrade::new(BasicGradeSettings {
                        exposure,
                        warmth,
                        tint,
                        ..Default::default()
                    })
                    .unwrap();
                    let white = g
                        .gains
                        .iter()
                        .zip(LUMA)
                        .map(|(v, w)| v.powf(2.4) * w)
                        .sum::<f64>();
                    assert!((white - exposure.exp2()).abs() < 1e-12);
                }
            }
        }
        let warm = BasicGrade::new(BasicGradeSettings {
            warmth: 1.0,
            ..Default::default()
        })
        .unwrap();
        assert!(warm.gains[0] > warm.gains[2]);
        let tint = BasicGrade::new(BasicGradeSettings {
            tint: 1.0,
            ..Default::default()
        })
        .unwrap();
        assert!(tint.gains[0] > tint.gains[1] && tint.gains[2] > tint.gains[1]);
    }
    #[test]
    fn desaturation_uses_video_luminance_and_clamps_only_rgb() {
        let g = BasicGrade::new(BasicGradeSettings {
            saturation: -1.0,
            ..Default::default()
        })
        .unwrap();
        assert_eq!(g.saturate([1.0, 0.0, 0.0]), [0.2126; 3]);
        let g = BasicGrade::new(BasicGradeSettings {
            saturation: 1.0,
            ..Default::default()
        })
        .unwrap();
        assert_eq!(g.saturate([1.0, 0.0, 0.0])[0], 1.0);
    }
}
