// SPDX-License-Identifier: GPL-3.0-or-later
#[path = "../../../src/rendering/basic_grade.rs"]
pub mod basic_grade;
#[path = "../../../src/rendering/queued_color.rs"]
pub mod queued_color;
#[cfg(test)]
mod queue_restore_color;
#[cfg(feature = "ocio-runtime")]
#[path = "../../../src/rendering/ocio_runtime.rs"]
pub mod ocio_runtime;
#[path = "../../../src/rendering/cube_lut.rs"]
pub mod cube_lut;
#[path = "../../../src/rendering/export_lut.rs"]
pub mod export_lut;
#[path = "../../../src/rendering/ffmpeg_encoder_color.rs"]
pub mod ffmpeg_encoder_color;
#[path = "../../../src/rendering/tone_curve.rs"]
pub mod tone_curve;

#[cfg(test)]
mod camera_format_matrix;

#[cfg(test)]
mod tests {
    use super::export_lut::ExportLut;
    use ffmpeg_next::{format::Pixel, frame::Video};

    fn cube(invert: bool) -> Vec<u8> {
        let mut text =
            String::from("TITLE \"Test\"\nLUT_3D_SIZE 2\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n");
        for b in 0..2 {
            for g in 0..2 {
                for r in 0..2 {
                    let values = if invert {
                        [1 - r, 1 - g, 1 - b]
                    } else {
                        [r, g, b]
                    };
                    text.push_str(&format!("{} {} {}\n", values[0], values[1], values[2]));
                }
            }
        }
        text.into_bytes()
    }

    fn floats(format: Pixel, width: u32, height: u32) -> Video {
        ffmpeg_next::init().unwrap();
        let mut frame = Video::new(format, width, height);
        frame.set_pts(Some(123456));
        for plane in 0..frame.planes() {
            let stride = frame.stride(plane);
            for y in 0..height as usize {
                for x in 0..width as usize {
                    let value = if plane == 3 {
                        0.375
                    } else {
                        (plane as f32 + x as f32 + 1.0) / 10.0
                    };
                    let offset = y * stride + x * 4;
                    frame.data_mut(plane)[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
                }
            }
        }
        frame
    }

    #[test]
    fn identity_preserves_float_precision_dimensions_and_timestamp() {
        let frame = floats(Pixel::GBRPF32LE, 8, 4);
        let output = ExportLut::new(&cube(false)).unwrap().apply(&frame).unwrap();
        assert_eq!(
            (
                output.format(),
                output.width(),
                output.height(),
                output.pts()
            ),
            (frame.format(), 8, 4, frame.pts())
        );
        for p in 0..3 {
            for y in 0..4 {
                for x in 0..8 {
                    let input = f32::from_le_bytes(
                        frame.data(p)[y * frame.stride(p) + x * 4..][..4]
                            .try_into()
                            .unwrap(),
                    );
                    let actual = f32::from_le_bytes(
                        output.data(p)[y * output.stride(p) + x * 4..][..4]
                            .try_into()
                            .unwrap(),
                    );
                    assert!((input - actual).abs() < 0.000001, "{input} != {actual}");
                }
            }
        }
    }

    #[test]
    fn chosen_transform_changes_rgb_and_preserves_alpha() {
        let frame = floats(Pixel::GBRAPF32LE, 8, 4);
        let output = ExportLut::new(&cube(true)).unwrap().apply(&frame).unwrap();
        for p in 0..4 {
            for y in 0..4 {
                for x in 0..8 {
                    let input = f32::from_le_bytes(
                        frame.data(p)[y * frame.stride(p) + x * 4..][..4]
                            .try_into()
                            .unwrap(),
                    );
                    let actual = f32::from_le_bytes(
                        output.data(p)[y * output.stride(p) + x * 4..][..4]
                            .try_into()
                            .unwrap(),
                    );
                    let expected = if p == 3 { input } else { 1.0 - input };
                    assert!(
                        (expected - actual).abs() < 0.000001,
                        "{expected} != {actual}"
                    );
                }
            }
        }
    }

    #[test]
    fn invalid_or_empty_lut_fails_instead_of_exporting_uncorrected_video() {
        assert!(ExportLut::new(b"").is_err());
        assert!(ExportLut::new(b"not a cube file").is_err());
    }

    #[test]
    fn graph_rebuilds_when_frame_size_changes() {
        let mut lut = ExportLut::new(&cube(false)).unwrap();
        for (w, h) in [(8, 4), (16, 8), (8, 4)] {
            let output = lut.apply(&floats(Pixel::GBRPF32LE, w, h)).unwrap();
            assert_eq!((output.width(), output.height()), (w, h));
        }
    }

    #[test]
    fn ten_bit_yuv_stays_ten_bit_and_keeps_color_properties() {
        ffmpeg_next::init().unwrap();
        let mut frame = Video::new(Pixel::YUV420P10LE, 16, 8);
        frame.set_color_space(ffmpeg_next::color::Space::BT709);
        frame.set_color_range(ffmpeg_next::color::Range::MPEG);
        for p in 0..3 {
            let (w, h) = if p == 0 { (16, 8) } else { (8, 4) };
            let stride = frame.stride(p);
            for y in 0..h {
                for x in 0..w {
                    let value: u16 = if p == 0 { 128 + x as u16 * 24 } else { 512 };
                    frame.data_mut(p)[y * stride + x * 2..][..2]
                        .copy_from_slice(&value.to_le_bytes());
                }
            }
        }
        let output = ExportLut::new(&cube(false)).unwrap().apply(&frame).unwrap();
        assert_eq!(output.format(), Pixel::YUV420P10LE);
        assert_eq!(output.color_space(), frame.color_space());
        assert_eq!(output.color_range(), frame.color_range());
        for x in 0..16 {
            let expected = u16::from_le_bytes(frame.data(0)[x * 2..][..2].try_into().unwrap());
            let actual = u16::from_le_bytes(output.data(0)[x * 2..][..2].try_into().unwrap());
            assert!(
                (expected as i32 - actual as i32).abs() <= 2,
                "{expected} != {actual}"
            );
        }
    }
    #[test]
    fn lut_preserves_non_square_pixel_geometry() {
        let mut frame = floats(Pixel::GBRPF32LE, 8, 4);
        unsafe {
            (*frame.as_mut_ptr()).sample_aspect_ratio =
                ffmpeg_next::ffi::AVRational { num: 4, den: 3 };
        }
        let output = ExportLut::new(&cube(false)).unwrap().apply(&frame).unwrap();
        assert_eq!(output.aspect_ratio(), frame.aspect_ratio());
    }

    #[test]
    fn adjustments_match_preview_formula_after_lut_and_preserve_alpha() {
        let frame = floats(Pixel::GBRAPF32LE, 8, 4);
        let mut filter = ExportLut::with_adjustments(Some(&cube(true)), 0.1, 0.2).unwrap();
        let output = filter.apply(&frame).unwrap();
        for p in 0..4 {
            for y in 0..4 {
                for x in 0..8 {
                    let input = f32::from_le_bytes(
                        frame.data(p)[y * frame.stride(p) + x * 4..][..4]
                            .try_into()
                            .unwrap(),
                    );
                    let actual = f32::from_le_bytes(
                        output.data(p)[y * output.stride(p) + x * 4..][..4]
                            .try_into()
                            .unwrap(),
                    );
                    let expected = if p == 3 {
                        input
                    } else {
                        ((1.0 - input - 0.5) * 1.2 + 0.6).clamp(0.0, 1.0)
                    };
                    assert!(
                        (actual - expected).abs() < 0.000001,
                        "{actual} != {expected}"
                    );
                }
            }
        }
        assert_eq!(output.pts(), frame.pts());
    }

    #[test]
    fn neutral_adjustments_without_lut_are_identity() {
        let frame = floats(Pixel::GBRPF32LE, 8, 4);
        let output = ExportLut::with_adjustments(None, 0.0, 0.0)
            .unwrap()
            .apply(&frame)
            .unwrap();
        for p in 0..3 {
            assert_eq!(frame.data(p), output.data(p));
        }
        assert!(ExportLut::with_adjustments(None, f64::NAN, 0.0).is_err());
        assert!(ExportLut::with_adjustments(None, 0.0, 0.51).is_err());
    }

    #[test]
    fn preview_atlas_keeps_every_float_bit_without_alpha_storage() {
        let cube = super::cube_lut::CubeLut::parse(&cube(true)).unwrap();
        let (_, _, atlas) = cube.atlas();
        for (i, entry) in cube.entries.iter().enumerate() {
            for (c, value) in entry.iter().enumerate() {
                let start = (i * 6 + c * 2) * 3;
                let decoded = f32::from_le_bytes([
                    atlas[start],
                    atlas[start + 1],
                    atlas[start + 2],
                    atlas[start + 3],
                ]);
                assert_eq!(decoded.to_bits(), value.to_bits());
            }
        }
        for invalid in [
            b"LUT_3D_SIZE 9999\n".as_slice(),
            b"LUT_3D_SIZE 2\nNaN 0 0\n",
            b"LUT_1D_SIZE 2\n",
            b"LUT_3D_SIZE 2\nDOMAIN_MAX 2 2 2\n",
        ] {
            assert!(super::cube_lut::CubeLut::parse(invalid).is_err());
        }
    }
    #[test]
    fn oversized_stream_is_bounded_before_parsing() {
        use std::io::Read;
        let mut input = std::io::repeat(b'0').take(128 * 1024 * 1024);
        assert!(super::cube_lut::CubeLut::read_bounded(&mut input).is_err());
        assert_eq!(input.limit(), 64 * 1024 * 1024 - 1);
    }
    #[test]
    fn adjustment_extremes_without_lut_clamp_rgb_and_preserve_alpha() {
        let frame = floats(Pixel::GBRAPF32LE, 8, 4);
        for brightness in [-0.5_f64, 0.5] {
            for contrast in [-0.5_f64, 0.5] {
                let output = ExportLut::with_adjustments(None, brightness, contrast)
                    .unwrap()
                    .apply(&frame)
                    .unwrap();
                for p in 0..4 {
                    for y in 0..4 {
                        for x in 0..8 {
                            let input = f32::from_le_bytes(
                                frame.data(p)[y * frame.stride(p) + x * 4..][..4]
                                    .try_into()
                                    .unwrap(),
                            );
                            let actual = f32::from_le_bytes(
                                output.data(p)[y * output.stride(p) + x * 4..][..4]
                                    .try_into()
                                    .unwrap(),
                            );
                            let expected = if p == 3 {
                                input
                            } else {
                                ((input - 0.5) * (1.0 + contrast as f32) + 0.5 + brightness as f32)
                                    .clamp(0.0, 1.0)
                            };
                            assert!(
                                (actual - expected).abs() < 0.000001,
                                "{actual} != {expected}"
                            );
                        }
                    }
                }
            }
        }
    }

    // Independent FFmpeg geq oracle: the previous export adjustment pipeline.
    fn geq_reference(frame: &Video, brightness: f64, contrast: f64) -> Video {
        use ffmpeg_next::{ffi, filter};
        let mut graph = filter::Graph::new();
        let pixel: ffi::AVPixelFormat = frame.format().into();
        let aspect = frame.aspect_ratio();
        let source_args = format!(
            "video_size={}x{}:pix_fmt={}:time_base=1/1000000:pixel_aspect={}/{}:colorspace={}:range={}",
            frame.width(),
            frame.height(),
            pixel as i32,
            aspect.numerator().max(1),
            aspect.denominator().max(1),
            frame.color_space() as i32,
            frame.color_range() as i32
        );
        graph
            .add(&filter::find("buffer").unwrap(), "in", &source_args)
            .unwrap();
        graph
            .add(&filter::find("buffersink").unwrap(), "out", "")
            .unwrap();
        let channels = ['r', 'g', 'b']
            .map(|c| {
                format!(
                    "{c}='clip(({c}(X,Y)-0.5)*{}+{},0,1)'",
                    1.0 + contrast,
                    0.5 + brightness
                )
            })
            .join(":");
        let alpha = frame.format() == Pixel::GBRAPF32LE;
        let name = unsafe { std::ffi::CStr::from_ptr(ffi::av_get_pix_fmt_name(pixel)) }
            .to_str()
            .unwrap();
        let filters = format!(
            "format={},geq={channels}:a='alpha(X,Y)':interpolation=nearest,format={name}",
            if alpha { "gbrapf32le" } else { "gbrpf32le" }
        );
        graph
            .output("in", 0)
            .unwrap()
            .input("out", 0)
            .unwrap()
            .parse(&filters)
            .unwrap();
        graph.validate().unwrap();
        let mut source = graph.get("in").unwrap();
        assert_eq!(
            unsafe {
                ffi::av_buffersrc_add_frame_flags(
                    source.as_mut_ptr(),
                    frame.as_ptr().cast_mut(),
                    ffi::AV_BUFFERSRC_FLAG_KEEP_REF as i32,
                )
            },
            0
        );
        let mut output = Video::empty();
        graph.get("out").unwrap().sink().frame(&mut output).unwrap();
        output
    }

    fn assert_active_pixels_equal(a: &Video, b: &Video) {
        assert_eq!(
            (
                a.format(),
                a.width(),
                a.height(),
                a.pts(),
                a.aspect_ratio(),
                a.color_space(),
                a.color_range()
            ),
            (
                b.format(),
                b.width(),
                b.height(),
                b.pts(),
                b.aspect_ratio(),
                b.color_space(),
                b.color_range()
            )
        );
        for p in 0..a.planes() {
            let row_bytes = match a.format() {
                Pixel::GBRPF32LE | Pixel::GBRAPF32LE => a.width() as usize * 4,
                Pixel::P010LE => a.width() as usize * 2,
                Pixel::YUV420P10LE => a.plane_width(p) as usize * 2,
                _ => panic!("Unexpected fixture format"),
            };
            for y in 0..a.plane_height(p) as usize {
                let left = &a.data(p)[y * a.stride(p)..][..row_bytes];
                let right = &b.data(p)[y * b.stride(p)..][..row_bytes];
                if cfg!(feature = "ocio-runtime") && p < 3
                    && matches!(a.format(), Pixel::GBRPF32LE | Pixel::GBRAPF32LE)
                {
                    // OCIO applies a float32 matrix; the legacy geq reference
                    // evaluates the same affine operation in float64. Bound
                    // their measured rounding difference, retaining exact alpha
                    // and integer-format comparisons.
                    for (l, r) in left.chunks_exact(4).zip(right.chunks_exact(4)) {
                        let l = f32::from_le_bytes(l.try_into().unwrap());
                        let r = f32::from_le_bytes(r.try_into().unwrap());
                        assert!((l-r).abs() <= 2e-7, "plane {p}, row {y}: {l} != {r}");
                    }
                } else {
                    assert_eq!(left, right, "plane {p}, row {y}");
                }
            }
        }
    }

    #[test]
    fn native_adjustments_match_geq_precision_and_do_not_mutate_shared_odd_width_frames() {
        let mut frame = floats(Pixel::GBRAPF32LE, 17, 5);
        for p in 0..4 {
            let stride = frame.stride(p);
            frame.data_mut(p).fill(0xA5);
            for y in 0..5 {
                for x in 0..17 {
                    let value = (x as f32 - 3.0) / 10.0 + p as f32 * 0.03;
                    frame.data_mut(p)[y * stride + x * 4..][..4]
                        .copy_from_slice(&value.to_le_bytes());
                }
            }
        }
        let saved: Vec<Vec<u8>> = (0..4).map(|p| frame.data(p).to_vec()).collect();
        for (brightness, contrast) in [
            (-0.5, -0.5),
            (0.5, 0.5),
            (0.0, 0.2),
            (0.1, 0.0),
            (0.1, 0.2),
            (-0.123, 0.234),
        ] {
            let reference = geq_reference(&frame, brightness, contrast);
            let mut filter = ExportLut::with_adjustments(None, brightness, contrast).unwrap();
            for _ in 0..2 {
                let output = filter.apply(&frame).unwrap();
                assert_active_pixels_equal(&reference, &output);
                for p in 0..4 {
                    assert_eq!(frame.data(p), saved[p]);
                }
            }
        }
    }

    #[test]
    fn adjusted_ten_bit_frames_match_geq_and_rebuild_for_format_size_and_color_changes() {
        ffmpeg_next::init().unwrap();
        let mut filter = ExportLut::with_adjustments(None, 0.1, 0.2).unwrap();
        for (pixel, w, h, space, range) in [
            (
                Pixel::YUV420P10LE,
                18,
                10,
                ffmpeg_next::color::Space::BT709,
                ffmpeg_next::color::Range::MPEG,
            ),
            (
                Pixel::P010LE,
                32,
                16,
                ffmpeg_next::color::Space::BT709,
                ffmpeg_next::color::Range::MPEG,
            ),
            (
                Pixel::YUV420P10LE,
                18,
                10,
                ffmpeg_next::color::Space::BT2020NCL,
                ffmpeg_next::color::Range::JPEG,
            ),
            (
                Pixel::YUV420P10LE,
                18,
                10,
                ffmpeg_next::color::Space::Unspecified,
                ffmpeg_next::color::Range::Unspecified,
            ),
        ] {
            let mut frame = Video::new(pixel, w, h);
            frame.set_pts(Some(98765));
            frame.set_color_space(space);
            frame.set_color_range(range);
            unsafe {
                (*frame.as_mut_ptr()).sample_aspect_ratio =
                    ffmpeg_next::ffi::AVRational { num: 4, den: 3 };
            }
            for p in 0..frame.planes() {
                let stride = frame.stride(p);
                let row_samples = if pixel == Pixel::P010LE {
                    w as usize
                } else {
                    frame.plane_width(p) as usize
                };
                for y in 0..frame.plane_height(p) as usize {
                    for x in 0..row_samples {
                        let value: u16 = ((x * 37 + y * 13 + p * 97) % 1024) as u16;
                        let stored = if pixel == Pixel::P010LE {
                            value << 6
                        } else {
                            value
                        };
                        frame.data_mut(p)[y * stride + x * 2..][..2]
                            .copy_from_slice(&stored.to_le_bytes());
                    }
                }
            }
            let saved: Vec<Vec<u8>> = (0..frame.planes())
                .map(|p| frame.data(p).to_vec())
                .collect();
            let reference = geq_reference(&frame, 0.1, 0.2);
            let output = filter.apply(&frame).unwrap();
            assert_active_pixels_equal(&reference, &output);
            let mut graded = ExportLut::with_grading(
                None,
                0.1,
                0.2,
                0.3,
                -0.4,
                super::basic_grade::BasicGradeSettings {
                    exposure: 0.37,
                    saturation: 0.23,
                    warmth: 0.41,
                    tint: -0.27,
                },
            )
            .unwrap();
            let graded_output = graded.apply(&frame).unwrap();
            assert_eq!(graded_output.format(), pixel);
            assert_eq!(
                (
                    graded_output.width(),
                    graded_output.height(),
                    graded_output.pts()
                ),
                (w, h, frame.pts())
            );
            assert_eq!(graded_output.color_space(), space);
            assert_eq!(graded_output.color_range(), range);
            assert_eq!(graded_output.aspect_ratio(), frame.aspect_ratio());
            for p in 0..frame.planes() {
                assert_eq!(frame.data(p), saved[p]);
            }
        }
    }
    #[test]
    fn neutral_added_controls_preserve_old_float_and_ten_bit_paths() {
        use super::basic_grade::BasicGradeSettings;
        for frame in [
            floats(Pixel::GBRAPF32LE, 17, 5),
            Video::new(Pixel::YUV420P10LE, 18, 10),
        ] {
            for lut in [None, Some(cube(false))] {
                for (b, c, sh, hi) in [(0.0, 0.0, 0.0, 0.0), (0.12, 0.18, 0.3, -0.4)] {
                    let old = ExportLut::with_color(lut.as_deref(), b, c, sh, hi)
                        .unwrap()
                        .apply(&frame)
                        .unwrap();
                    let new = ExportLut::with_grading(
                        lut.as_deref(),
                        b,
                        c,
                        sh,
                        hi,
                        BasicGradeSettings::default(),
                    )
                    .unwrap()
                    .apply(&frame)
                    .unwrap();
                    assert_active_pixels_equal(&old, &new);
                }
            }
        }
    }

    #[test]
    fn saturation_combines_rgb_without_mutating_shared_alpha_or_padding() {
        use super::basic_grade::BasicGradeSettings;
        let mut frame = floats(Pixel::GBRAPF32LE, 17, 5);
        for p in 0..4 {
            let stride = frame.stride(p);
            frame.data_mut(p).fill(0xa5);
            for y in 0..5 {
                for x in 0..17 {
                    let value: f32 = if p == 2 {
                        1.0
                    } else if p == 3 {
                        0.375
                    } else {
                        0.0
                    };
                    frame.data_mut(p)[y * stride + x * 4..][..4]
                        .copy_from_slice(&value.to_le_bytes());
                }
            }
        }
        let saved: Vec<_> = (0..4).map(|p| frame.data(p).to_vec()).collect();
        let mut filter = ExportLut::with_grading(
            None,
            0.0,
            0.0,
            0.0,
            0.0,
            BasicGradeSettings {
                saturation: -1.0,
                ..Default::default()
            },
        )
        .unwrap();
        for _ in 0..3 {
            let output = filter.apply(&frame).unwrap();
            for p in 0..4 {
                assert_eq!(frame.data(p), saved[p]);
                for y in 0..5 {
                    for x in 0..17 {
                        let actual = f32::from_le_bytes(
                            output.data(p)[y * output.stride(p) + x * 4..][..4]
                                .try_into()
                                .unwrap(),
                        );
                        assert_eq!(actual, if p == 3 { 0.375 } else { 0.2126 });
                    }
                }
            }
            assert_eq!(output.pts(), frame.pts());
        }
    }


    #[cfg(feature = "ocio-runtime")]
    fn nonlinear_cube() -> Vec<u8> {
        let mut text = String::from("TITLE \"Nonlinear transition test\"\nLUT_3D_SIZE 3\n");
        for b in 0..3 {
            for g in 0..3 {
                for r in 0..3 {
                    let [r, g, b] = [r as f32 * 0.5, g as f32 * 0.5, b as f32 * 0.5];
                    text.push_str(&format!("{} {} {}\n",
                        0.8 * r * r + 0.1 * g + 0.05,
                        0.7 * g * g + 0.2 * b + 0.04,
                        0.75 * b * b + 0.15 * r + 0.03));
                }
            }
        }
        text.into_bytes()
    }

    // Independent FFmpeg reference: one graph, explicit source/destination YUV
    // conversion, official tetrahedral lut3d, then the former float64 geq grade.
    // The file option is set through FFmpeg's API, avoiding path expression escaping.
    #[cfg(feature = "ocio-runtime")]
    fn lut_geq_yuv_reference(frame: &Video, cube: &[u8], brightness: f64, contrast: f64) -> Video {
        use ffmpeg_next::{ffi, filter};
        use std::{ffi::{CStr, CString}, io::Write};
        let mut file = tempfile::Builder::new().suffix(".cube").tempfile().unwrap();
        file.write_all(cube).unwrap();
        file.flush().unwrap();
        let mut graph = filter::Graph::new();
        let pixel: ffi::AVPixelFormat = frame.format().into();
        let aspect = frame.aspect_ratio();
        let matrix = frame.color_space() as i32;
        let range = frame.color_range() as i32;
        graph.add(&filter::find("buffer").unwrap(), "in", &format!(
            "video_size={}x{}:pix_fmt={}:time_base=1/1000000:pixel_aspect={}/{}:colorspace={matrix}:range={range}",
            frame.width(), frame.height(), pixel as i32, aspect.numerator(), aspect.denominator()
        )).unwrap();
        graph.add(&filter::find("buffersink").unwrap(), "out", "").unwrap();
        let lut_filter = filter::find("lut3d").unwrap();
        let path = CString::new(file.path().to_str().unwrap()).unwrap();
        unsafe {
            let lut = ffi::avfilter_graph_alloc_filter(graph.as_mut_ptr(), lut_filter.as_ptr(), c"lut".as_ptr());
            assert!(!lut.is_null());
            assert_eq!(ffi::av_opt_set(lut.cast(), c"file".as_ptr(), path.as_ptr(), ffi::AV_OPT_SEARCH_CHILDREN), 0);
            assert_eq!(ffi::av_opt_set_int(lut.cast(), c"interp".as_ptr(), 2, ffi::AV_OPT_SEARCH_CHILDREN), 0);
            assert_eq!(ffi::avfilter_init_str(lut, std::ptr::null()), 0);
        }
        graph.output("in", 0).unwrap().input("lut", 0).unwrap().parse(&format!(
            "[in]scale=in_color_matrix={matrix}:in_range={range}:out_range=full,format=gbrpf32le[lut]"
        )).unwrap();
        let channels = ['r', 'g', 'b'].map(|c| format!(
            "{c}='clip(({c}(X,Y)-0.5)*{}+{},0,1)'", 1.0 + contrast, 0.5 + brightness
        )).join(":");
        let pixel_name = unsafe { CStr::from_ptr(ffi::av_get_pix_fmt_name(pixel)) }.to_str().unwrap();
        graph.output("lut", 0).unwrap().input("out", 0).unwrap().parse(&format!(
            "[lut]geq={channels}:interpolation=nearest,scale=out_color_matrix={matrix}:out_range={range},format={pixel_name}[out]"
        )).unwrap();
        graph.validate().unwrap();
        assert_eq!(unsafe {
            ffi::av_buffersrc_add_frame_flags(graph.get("in").unwrap().as_mut_ptr(),
                frame.as_ptr().cast_mut(), ffi::AV_BUFFERSRC_FLAG_KEEP_REF as i32)
        }, 0);
        let mut output = Video::empty();
        graph.get("out").unwrap().sink().frame(&mut output).unwrap();
        output
    }

    #[cfg(feature = "ocio-runtime")]
    #[test]
    fn ocio_lut_grade_preserves_yuv_depth_matrix_range_and_size_transitions() {
        use ffmpeg_next::color::{Range, Space};
        let cube = nonlinear_cube();
        let mut filter = ExportLut::with_adjustments(Some(&cube), 0.07, -0.11).unwrap();
        let mut worst = 0u16;
        let cases = [
            (Pixel::YUV420P, 18, 10, Space::BT709, Range::MPEG),
            (Pixel::YUV420P10LE, 34, 18, Space::BT2020NCL, Range::JPEG),
            (Pixel::YUV420P, 34, 18, Space::BT709, Range::JPEG),
            (Pixel::YUV420P10LE, 20, 14, Space::BT709, Range::MPEG),
            (Pixel::YUV420P10LE, 18, 10, Space::BT2020NCL, Range::MPEG),
            (Pixel::YUV420P10LE, 34, 18, Space::BT709, Range::JPEG),
            (Pixel::YUV420P, 18, 10, Space::BT709, Range::MPEG),
        ];
        for _ in 0..2 {
            for (pixel, width, height, space, range) in cases {
                let ten_bit = pixel == Pixel::YUV420P10LE;
                let mut frame = Video::new(pixel, width, height);
                frame.set_pts(Some(987654));
                frame.set_color_space(space);
                frame.set_color_range(range);
                unsafe { (*frame.as_mut_ptr()).sample_aspect_ratio = ffmpeg_next::ffi::AVRational {num: 4, den: 3}; }
                for p in 0..3 {
                    frame.data_mut(p).fill(0xa5);
                    let (low, high) = if range == Range::JPEG {
                        (0, if ten_bit {1023} else {255})
                    } else if p == 0 {
                        if ten_bit {(64, 940)} else {(16, 235)}
                    } else if ten_bit {(64, 960)} else {(16, 240)};
                    let bytes = if ten_bit {2} else {1};
                    for y in 0..frame.plane_height(p) as usize {
                        for x in 0..frame.plane_width(p) as usize {
                            let value = (low + (x * 37 + y * 23 + p * 71) % (high - low + 1)) as u16;
                            let offset = y * frame.stride(p) + x * bytes;
                            if ten_bit { frame.data_mut(p)[offset..][..2].copy_from_slice(&value.to_le_bytes()); }
                            else { frame.data_mut(p)[offset] = value as u8; }
                        }
                    }
                }
                let saved: Vec<_> = (0..3).map(|p| frame.data(p).to_vec()).collect();
                let expected = lut_geq_yuv_reference(&frame, &cube, 0.07, -0.11);
                let output = filter.apply(&frame).unwrap();
                assert_eq!((output.format(), output.width(), output.height(), output.pts(),
                    output.color_space(), output.color_range(), output.aspect_ratio()),
                    (pixel, width, height, frame.pts(), space, range, frame.aspect_ratio()));
                for p in 0..3 {
                    assert_eq!(frame.data(p), saved[p], "source plane {p}");
                    for y in 0..frame.plane_height(p) as usize {
                        for x in 0..frame.plane_width(p) as usize {
                            let sample = |image: &Video| -> u16 {
                                let offset = y * image.stride(p) + x * if ten_bit {2} else {1};
                                if ten_bit {u16::from_le_bytes(image.data(p)[offset..][..2].try_into().unwrap())}
                                else {image.data(p)[offset] as u16}
                            };
                            let delta = sample(&output).abs_diff(sample(&expected));
                            worst = worst.max(delta);
                            assert!(delta <= 1, "{pixel:?} {space:?} {range:?} {width}x{height}, plane {p}, {x},{y}: difference {delta} codes");
                        }
                    }
                }
            }
        }
        eprintln!("Combined nonlinear LUT + B/C YUV transitions: worst difference {worst} code(s)");
    }

    #[cfg(feature = "ocio-runtime")]
    mod ocio_layout {
        use super::floats;
        use crate::ocio_runtime::{OcioProcessor, Settings};
        use ffmpeg_next::{ffi, format::Pixel, frame::Video};
        use std::{ptr, sync::Arc};

        fn settings() -> Settings {
            Settings {
                brightness: 0.07,
                contrast: -0.11,
                shadows: 0.23,
                highlights: -0.28,
                exposure: 0.4,
                saturation: 0.15,
                warmth: 0.2,
                tint: -0.3,
            }
        }

        fn fill(frame: &mut Video) {
            let width = frame.width() as usize;
            let height = frame.height() as usize;
            for p in 0..frame.planes() {
                let stride = frame.stride(p);
                frame.data_mut(p).fill(0xa5);
                for y in 0..height {
                    for x in 0..width {
                        let value = ((x * 7 + y * 11 + p * 13) % 89 + 5) as f32 / 100.0;
                        frame.data_mut(p)[y * stride + x * 4..][..4]
                            .copy_from_slice(&value.to_le_bytes());
                    }
                }
            }
        }

        fn active_bytes(frame: &Video) -> Vec<Vec<u8>> {
            let row_bytes = frame.width() as usize * 4;
            (0..frame.planes()).map(|p| {
                (0..frame.height() as usize).flat_map(|y| {
                    frame.data(p)[y * frame.stride(p)..][..row_bytes].iter().copied()
                }).collect()
            }).collect()
        }

        // Restore all fields before AVFrame is dropped, even if a test panics.
        // Never use ffmpeg-next slice helpers while the raw layout is malformed.
        struct RestoreLayout {
            frame: *mut ffi::AVFrame,
            data: [*mut u8; 8],
            linesize: [i32; 8],
            buffers: [*mut ffi::AVBufferRef; 8],
            buffer_sizes: [usize; 8],
            width: i32,
            height: i32,
        }
        impl RestoreLayout {
            unsafe fn new(frame: *mut ffi::AVFrame) -> Self {
                let raw = unsafe { &*frame };
                Self {
                    frame, data: raw.data, linesize: raw.linesize, buffers: raw.buf,
                    buffer_sizes: std::array::from_fn(|p| {
                        if raw.buf[p].is_null() { 0 } else { unsafe { (*raw.buf[p]).size } }
                    }),
                    width: raw.width, height: raw.height,
                }
            }
        }
        impl Drop for RestoreLayout {
            fn drop(&mut self) {
                unsafe {
                    let raw = &mut *self.frame;
                    raw.data = self.data;
                    raw.linesize = self.linesize;
                    raw.buf = self.buffers;
                    raw.width = self.width;
                    raw.height = self.height;
                    for p in 0..8 {
                        if !self.buffers[p].is_null() {
                            (*self.buffers[p]).size = self.buffer_sizes[p];
                        }
                    }
                }
            }
        }

        #[test]
        fn ocio_rejects_malformed_owned_plane_layouts_before_touching_pixels() {
            let processor = OcioProcessor::new(settings()).unwrap();
            for case in [
                "negative stride", "zero stride", "unaligned stride", "short stride",
                "null data", "unaligned data", "unbacked data", "short owner",
                "span past owner", "RGB overlap", "alpha aliases RGB",
                "negative width", "empty height",
            ] {
                let mut frame = floats(Pixel::GBRAPF32LE, 17, 5);
                fill(&mut frame);
                let saved: Vec<_> = (0..4).map(|p| frame.data(p).to_vec()).collect();
                let result = unsafe {
                    let raw = frame.as_mut_ptr();
                    let guard = RestoreLayout::new(raw);
                    match case {
                        "negative stride" => (*raw).linesize[0] = -(*raw).linesize[0],
                        "zero stride" => (*raw).linesize[0] = 0,
                        "unaligned stride" => (*raw).linesize[0] += 1,
                        "short stride" => (*raw).linesize[0] = 16 * 4,
                        "null data" => (*raw).data[0] = ptr::null_mut(),
                        "unaligned data" => (*raw).data[0] = (*raw).data[0].add(1),
                        "unbacked data" => (*raw).buf = [ptr::null_mut(); 8],
                        "short owner" => {
                            let owner = ffi::av_frame_get_plane_buffer(raw, 0);
                            assert!(!owner.is_null());
                            (*owner).size = ((*raw).data[0] as usize - (*owner).data as usize) + 4;
                        },
                        "span past owner" => (*raw).height = 1000,
                        "RGB overlap" => (*raw).data[1] = (*raw).data[0],
                        "alpha aliases RGB" => (*raw).data[3] = (*raw).data[2],
                        "negative width" => (*raw).width = -1,
                        "empty height" => (*raw).height = 0,
                        _ => unreachable!(),
                    }
                    let result = processor.apply_frame(&mut frame);
                    drop(guard);
                    result
                };
                assert!(result.is_err(), "accepted malformed layout: {case}");
                for p in 0..4 {
                    assert_eq!(frame.data(p), saved[p], "{case} changed plane {p}");
                }
            }
        }

        #[test]
        fn ocio_rejects_non_float_input_without_mutation() {
            let processor = OcioProcessor::new(settings()).unwrap();
            let mut frame = Video::new(Pixel::YUV420P10LE, 18, 10);
            for p in 0..frame.planes() { frame.data_mut(p).fill(0xa5); }
            let saved: Vec<_> = (0..frame.planes()).map(|p| frame.data(p).to_vec()).collect();
            assert!(processor.apply_frame(&mut frame).is_err());
            for p in 0..frame.planes() { assert_eq!(frame.data(p), saved[p]); }
        }

        #[test]
        fn ocio_copy_on_write_keeps_shared_source_and_alpha_exact() {
            let processor = OcioProcessor::new(settings()).unwrap();
            let mut source = floats(Pixel::GBRAPF32LE, 17, 5);
            fill(&mut source);
            source.set_color_space(ffmpeg_next::color::Space::BT709);
            source.set_color_range(ffmpeg_next::color::Range::JPEG);
            let saved: Vec<_> = (0..4).map(|p| source.data(p).to_vec()).collect();
            let source_active = active_bytes(&source);
            let mut expected = source.clone();
            processor.apply_frame(&mut expected).unwrap();
            let mut shared = Video::empty();
            unsafe {
                assert_eq!(ffi::av_frame_ref(shared.as_mut_ptr(), source.as_ptr()), 0);
                assert_eq!((*shared.as_ptr()).data, (*source.as_ptr()).data);
                assert_eq!(ffi::av_frame_is_writable(shared.as_ptr().cast_mut()), 0);
            }
            processor.apply_frame(&mut shared).unwrap();
            unsafe {
                assert_ne!((*shared.as_ptr()).data[0], (*source.as_ptr()).data[0]);
                assert_eq!(ffi::av_frame_is_writable(shared.as_ptr().cast_mut()), 1);
            }
            for p in 0..4 { assert_eq!(source.data(p), saved[p], "source plane {p}"); }
            assert_eq!(active_bytes(&shared), active_bytes(&expected));
            assert_eq!(active_bytes(&shared)[3], source_active[3]);
            assert_eq!(shared.pts(), source.pts());
            assert_eq!(shared.color_space(), source.color_space());
            assert_eq!(shared.color_range(), source.color_range());
        }

        // Each plane gets its own FFmpeg-owned buffer so their strides may differ.
        // This exercises the C++ bridge's row descriptor fallback, not just the
        // usual equal-stride fast path.
        fn unequal_stride_frame(width: u32, height: u32) -> Video {
            let mut frame = Video::empty();
            frame.set_format(Pixel::GBRAPF32LE);
            frame.set_width(width);
            frame.set_height(height);
            frame.set_pts(Some(123456));
            unsafe {
                let raw = frame.as_mut_ptr();
                for p in 0..4 {
                    let stride = width as usize * 4 + (p + 1) * 12;
                    let buffer = ffi::av_buffer_alloc(stride * height as usize);
                    assert!(!buffer.is_null());
                    (*raw).buf[p] = buffer;
                    (*raw).data[p] = (*buffer).data;
                    (*raw).linesize[p] = stride as i32;
                }
            }
            fill(&mut frame);
            frame
        }

        #[test]
        fn ocio_unequal_strides_preserve_odd_width_padding_and_alpha() {
            let processor = OcioProcessor::new(settings()).unwrap();
            let mut padded = unequal_stride_frame(17, 11);
            let saved: Vec<_> = (0..4).map(|p| padded.data(p).to_vec()).collect();
            let source_alpha = active_bytes(&padded)[3].clone();
            let mut expected = floats(Pixel::GBRAPF32LE, 17, 11);
            fill(&mut expected);
            processor.apply_frame(&mut expected).unwrap();
            processor.apply_frame(&mut padded).unwrap();
            assert_eq!(active_bytes(&padded), active_bytes(&expected));
            assert_eq!(active_bytes(&padded)[3], source_alpha);
            for p in 0..4 {
                for y in 0..11 {
                    let start = y * padded.stride(p) + 17 * 4;
                    let end = (y + 1) * padded.stride(p);
                    assert_eq!(&padded.data(p)[start..end], &saved[p][start..end],
                        "padding of plane {p}, row {y}");
                }
            }
            assert_eq!(padded.pts(), Some(123456));
        }

        #[test]
        fn ocio_gpu_resources_are_stable_finite_and_neutral_has_no_texture() {
            use std::io::Write;
            let mut file = tempfile::Builder::new().suffix(".cube").tempfile().unwrap();
            file.write_all(&super::nonlinear_cube()).unwrap();
            file.flush().unwrap();
            let processor = Arc::new(OcioProcessor::with_lut(settings(), Some(file.path())).unwrap());
            let resources: Vec<_> = std::thread::scope(|scope| {
                (0..4).map(|_| {
                    let processor = Arc::clone(&processor);
                    scope.spawn(move || processor.gpu_resources().unwrap())
                }).collect::<Vec<_>>().into_iter().map(|h| h.join().unwrap()).collect()
            });
            let expected = &resources[0];
            let texture = expected.texture.as_ref().expect("nonlinear cube needs one 3D texture");
            assert_eq!(texture.edge, 3);
            assert_eq!(texture.values.len(), 3 * 3 * 3 * 3);
            assert!(texture.values.iter().all(|v| v.is_finite()));
            assert!(expected.text.contains("applyOcioGrade"));
            assert!(expected.text.contains("layout(binding = 2) uniform sampler3D ocioLutTexture;"));
            for result in resources.iter().skip(1) {
                assert_eq!(result.text, expected.text);
                let actual = result.texture.as_ref().unwrap();
                assert_eq!(actual.edge, texture.edge);
                assert_eq!(actual.values, texture.values);
            }
            for _ in 0..3 {
                let result = processor.gpu_resources().unwrap();
                assert_eq!(result.text, expected.text);
                assert_eq!(result.texture.unwrap().values, texture.values);
            }
            let neutral = OcioProcessor::new(Settings::default()).unwrap();
            assert!(!neutral.is_active());
            assert!(neutral.gpu_resources().unwrap().texture.is_none());
            let grade_only = OcioProcessor::new(settings()).unwrap();
            assert!(grade_only.gpu_resources().unwrap().texture.is_none());
        }

        #[test]
        fn ocio_missing_lut_file_fails_without_creating_processor() {
            let directory = tempfile::tempdir().unwrap();
            let path = directory.path().join("missing.cube");
            assert!(!path.exists());
            let error = match OcioProcessor::with_lut(settings(), Some(&path)) {
                Ok(_) => panic!("missing LUT file created a processor"),
                Err(error) => error,
            };
            assert!(!error.is_empty());
            assert!(!path.exists());
        }

        #[test]
        fn ocio_shared_processor_is_deterministic_under_repeated_concurrent_use() {
            let processor = Arc::new(OcioProcessor::new(settings()).unwrap());
            let sizes = [(17, 5), (33, 19), (19, 17), (65, 9)];
            let expected: Vec<_> = sizes.iter().map(|&(w, h)| {
                let mut frame = floats(Pixel::GBRAPF32LE, w, h);
                fill(&mut frame);
                processor.apply_frame(&mut frame).unwrap();
                active_bytes(&frame)
            }).collect();
            std::thread::scope(|scope| {
                let mut handles = Vec::new();
                for (index, &(w, h)) in sizes.iter().enumerate() {
                    let processor = Arc::clone(&processor);
                    let reference = &expected[index];
                    handles.push(scope.spawn(move || {
                        for repetition in 0..24 {
                            let mut frame = floats(Pixel::GBRAPF32LE, w, h);
                            fill(&mut frame);
                            let before = active_bytes(&frame);
                            processor.apply_frame(&mut frame).unwrap();
                            assert_eq!(&active_bytes(&frame), reference,
                                "thread {index}, repetition {repetition}");
                            assert_eq!(active_bytes(&frame)[3], before[3]);
                        }
                    }));
                }
                for handle in handles { handle.join().unwrap(); }
            });
        }
    }
}
