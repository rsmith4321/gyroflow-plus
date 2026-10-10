// SPDX-License-Identifier: GPL-3.0-or-later
//! Camera, range and format regression matrix for the export colour path.
//!
//! Every frame here is synthetic and uniform. The expected values come from
//! the published Y'CbCr equations (BT.601/709/2020 Kr,Kb and the 8/10-bit
//! limited and full quantisation), not from another FFmpeg graph, so a change
//! in FFmpeg's matrix or range defaults is caught rather than mirrored.
//! Synthetic tags prove the code path only; they are not real-camera support.
use crate::{cube_lut::CubeLut, export_lut::ExportLut};
use ffmpeg_next::{
    color::{Range, Space},
    format::Pixel,
    frame::Video,
};

/// FFmpeg 9.0.x decodes an untagged (unspecified) Y'CbCr matrix with the
/// BT.601 coefficients (libswscale/yuv2rgb.c:50, graph.c:598). This pins that
/// characterisation; change it only together with a deliberate product
/// decision about untagged footage.
const UNTAGGED_MATRIX: Space = Space::SMPTE170M;

/// Non-idempotent gray LUT: every channel becomes OFFSET + GAIN * red.
/// Applying it twice is distinguishable from once, and its gray output
/// makes the encoded luma independent of the output matrix.
const OFFSET: f64 = 0.25;
const GAIN: f64 = 0.7;

fn gray_from_red_cube() -> Vec<u8> {
    let mut text = String::from("TITLE \"gray from red\"\nLUT_3D_SIZE 2\n");
    for _b in 0..2 {
        for _g in 0..2 {
            for r in 0..2 {
                let v = OFFSET + GAIN * r as f64;
                text.push_str(&format!("{v} {v} {v}\n"));
            }
        }
    }
    text.into_bytes()
}

/// Constant colour LUT: the output Y'CbCr exposes the restore matrix.
const CONSTANT: [f64; 3] = [0.8, 0.3, 0.1];

fn constant_cube() -> Vec<u8> {
    let mut text = String::from("LUT_3D_SIZE 2\n");
    for _ in 0..8 {
        text.push_str(&format!(
            "{} {} {}\n",
            CONSTANT[0], CONSTANT[1], CONSTANT[2]
        ));
    }
    text.into_bytes()
}

fn coefficients(space: Space) -> (f64, f64) {
    match space {
        Space::BT709 => (0.2126, 0.0722),
        Space::SMPTE170M | Space::BT470BG => (0.299, 0.114),
        Space::BT2020NCL => (0.2627, 0.0593),
        Space::Unspecified => coefficients(UNTAGGED_MATRIX),
        other => panic!("No reference coefficients for {other:?}"),
    }
}

#[derive(Clone, Copy, Debug)]
enum Layout {
    Planar,     // Y, Cb, Cr (and A) in separate planes
    SemiPlanar, // Y plane, interleaved CbCr plane (NV12/P010)
}

#[derive(Clone, Copy, Debug)]
struct Format {
    bits: u32,
    layout: Layout,
    msb_aligned: bool, // P010 stores 10 bits in the high bits
    alpha: bool,
}

fn format(pixel: Pixel) -> Format {
    let (bits, layout, msb_aligned, alpha) = match pixel {
        Pixel::YUV420P | Pixel::YUVJ420P | Pixel::YUV422P | Pixel::YUVJ422P => {
            (8, Layout::Planar, false, false)
        }
        Pixel::YUV420P10LE | Pixel::YUV422P10LE => (10, Layout::Planar, false, false),
        Pixel::YUVA444P10LE => (10, Layout::Planar, false, true),
        Pixel::NV12 => (8, Layout::SemiPlanar, false, false),
        Pixel::P010LE => (10, Layout::SemiPlanar, true, false),
        other => panic!("Unexpected fixture format {other:?}"),
    };
    Format {
        bits,
        layout,
        msb_aligned,
        alpha,
    }
}

fn full_range(pixel: Pixel, range: Range) -> bool {
    range == Range::JPEG || matches!(pixel, Pixel::YUVJ420P | Pixel::YUVJ422P)
}

/// Quantise normalised Y' (0..1) and Pb/Pr (-0.5..0.5) to code values.
fn encode(bits: u32, full: bool, y: f64, pb: f64, pr: f64) -> [f64; 3] {
    let scale = (1u32 << (bits - 8)) as f64;
    if full {
        let max = ((1u32 << bits) - 1) as f64;
        let mid = (1u32 << (bits - 1)) as f64;
        [y * max, mid + pb * max, mid + pr * max]
    } else {
        [
            (16.0 + 219.0 * y) * scale,
            (128.0 + 224.0 * pb) * scale,
            (128.0 + 224.0 * pr) * scale,
        ]
    }
}

fn decode_red(bits: u32, full: bool, codes: [f64; 3], space: Space) -> f64 {
    let (kr, _) = coefficients(space);
    let scale = (1u32 << (bits - 8)) as f64;
    let (y, pr) = if full {
        let max = ((1u32 << bits) - 1) as f64;
        let mid = (1u32 << (bits - 1)) as f64;
        (codes[0] / max, (codes[2] - mid) / max)
    } else {
        (
            (codes[0] / scale - 16.0) / 219.0,
            (codes[2] / scale - 128.0) / 224.0,
        )
    };
    y + 2.0 * (1.0 - kr) * pr
}

fn rgb_to_ypbpr(rgb: [f64; 3], space: Space) -> (f64, f64, f64) {
    let (kr, kb) = coefficients(space);
    let y = kr * rgb[0] + (1.0 - kr - kb) * rgb[1] + kb * rgb[2];
    (
        y,
        (rgb[2] - y) / (2.0 * (1.0 - kb)),
        (rgb[0] - y) / (2.0 * (1.0 - kr)),
    )
}

fn write_sample(
    frame: &mut Video,
    f: &Format,
    plane: usize,
    index: usize,
    offset: usize,
    value: u16,
) {
    let stride = frame.stride(plane);
    let data = frame.data_mut(plane);
    if f.bits == 8 {
        data[offset * stride + index] = value as u8;
    } else {
        let stored = if f.msb_aligned { value << 6 } else { value };
        data[offset * stride + index * 2..][..2].copy_from_slice(&stored.to_le_bytes());
    }
}

fn read_sample(frame: &Video, f: &Format, plane: usize, index: usize, row: usize) -> u16 {
    let stride = frame.stride(plane);
    let data = frame.data(plane);
    if f.bits == 8 {
        data[row * stride + index] as u16
    } else {
        let raw = u16::from_le_bytes(data[row * stride + index * 2..][..2].try_into().unwrap());
        if f.msb_aligned {
            assert_eq!(raw & 0x3f, 0, "P010 low six bits must stay zero");
            raw >> 6
        } else {
            raw
        }
    }
}

/// Uniform frame with the given Y, Cb, Cr (and alpha) codes.
fn uniform(pixel: Pixel, space: Space, range: Range, codes: [u16; 3], alpha: u16) -> Video {
    ffmpeg_next::init().unwrap();
    let f = format(pixel);
    let (w, h) = (18u32, 10u32);
    let mut frame = Video::new(pixel, w, h);
    frame.set_pts(Some(424242));
    frame.set_color_space(space);
    frame.set_color_range(range);
    unsafe {
        (*frame.as_mut_ptr()).sample_aspect_ratio = ffmpeg_next::ffi::AVRational { num: 4, den: 3 };
    }
    match f.layout {
        Layout::Planar => {
            for p in 0..frame.planes() {
                let value = if p == 3 { alpha } else { codes[p] };
                for y in 0..frame.plane_height(p) as usize {
                    for x in 0..frame.plane_width(p) as usize {
                        write_sample(&mut frame, &f, p, x, y, value);
                    }
                }
            }
        }
        Layout::SemiPlanar => {
            for y in 0..h as usize {
                for x in 0..w as usize {
                    write_sample(&mut frame, &f, 0, x, y, codes[0]);
                }
            }
            for y in 0..(h as usize).div_ceil(2) {
                for x in 0..(w as usize).div_ceil(2) {
                    write_sample(&mut frame, &f, 1, x * 2, y, codes[1]);
                    write_sample(&mut frame, &f, 1, x * 2 + 1, y, codes[2]);
                }
            }
        }
    }
    frame
}

/// (min, max) of each component over the active picture: Y, Cb, Cr, A.
fn component_ranges(frame: &Video) -> Vec<(u16, u16)> {
    let f = format(frame.format());
    let mut ranges = vec![(u16::MAX, 0u16); if f.alpha { 4 } else { 3 }];
    let mut note = |c: usize, v: u16| {
        ranges[c] = (ranges[c].0.min(v), ranges[c].1.max(v));
    };
    match f.layout {
        Layout::Planar => {
            for p in 0..frame.planes() {
                for y in 0..frame.plane_height(p) as usize {
                    for x in 0..frame.plane_width(p) as usize {
                        note(p, read_sample(frame, &f, p, x, y));
                    }
                }
            }
        }
        Layout::SemiPlanar => {
            for y in 0..frame.height() as usize {
                for x in 0..frame.width() as usize {
                    note(0, read_sample(frame, &f, 0, x, y));
                }
            }
            for y in 0..(frame.height() as usize).div_ceil(2) {
                for x in 0..(frame.width() as usize).div_ceil(2) {
                    note(1, read_sample(frame, &f, 1, x * 2, y));
                    note(2, read_sample(frame, &f, 1, x * 2 + 1, y));
                }
            }
        }
    }
    ranges
}

/// Integer rounding of the true value (half a code) plus libswscale's
/// fixed-point coefficients (measured up to ~1.03 codes at 8 bits for
/// BT.2020 full range): 1.5 codes at 8 bits, 4 codes (one 8-bit step)
/// at 10 bits. A wrong matrix or range moves these fixtures by 6+ codes.
fn tolerance(bits: u32) -> f64 {
    if bits == 8 { 1.5 } else { 4.0 }
}

fn assert_close(label: &str, component: &str, range: (u16, u16), expected: f64, tol: f64) {
    if let Some(problem) = mismatch(label, component, range, expected, tol) {
        panic!("{problem}");
    }
}

fn mismatch(
    label: &str,
    component: &str,
    (lo, hi): (u16, u16),
    expected: f64,
    tol: f64,
) -> Option<String> {
    let worst = (lo as f64 - expected)
        .abs()
        .max((hi as f64 - expected).abs());
    (worst > tol)
        .then(|| format!("{label}: {component} codes {lo}..={hi}, expected {expected:.2} ±{tol}"))
}

fn report(test: &str, problems: Vec<String>) {
    assert!(
        problems.is_empty(),
        "{test}: {} mismatches\n{}",
        problems.len(),
        problems.join("\n")
    );
}

/// The brightness/contrast stage, as documented and tested elsewhere:
/// clip((x - 0.5) * (1 + contrast) + 0.5 + brightness, 0, 1).
fn grade(v: f64, brightness: f64, contrast: f64) -> f64 {
    ((v - 0.5) * (1.0 + contrast) + 0.5 + brightness).clamp(0.0, 1.0)
}

struct Case {
    pixel: Pixel,
    space: Space,
    range: Range,
}

/// The camera-relevant decode targets: 8-bit 4:2:0 limited/full (H.264/HEVC
/// SDR from action cameras), YUVJ (FFmpeg's full-range H.264/HEVC 8-bit
/// decode), NV12/P010 (hardware decode and hardware encoder targets), 10-bit
/// 4:2:0 (HEVC 10-bit), 4:2:2 10-bit and 4:4:4:4 10-bit (ProRes targets).
fn matrix_cases() -> Vec<Case> {
    let mut cases = Vec::new();
    for space in [
        Space::BT709,
        Space::SMPTE170M,
        Space::BT470BG,
        Space::BT2020NCL,
        Space::Unspecified,
    ] {
        for range in [Range::MPEG, Range::JPEG] {
            for pixel in [
                Pixel::YUV420P,
                Pixel::NV12,
                Pixel::YUV420P10LE,
                Pixel::P010LE,
                Pixel::YUV422P10LE,
                Pixel::YUVA444P10LE,
            ] {
                cases.push(Case {
                    pixel,
                    space,
                    range,
                });
            }
        }
        cases.push(Case {
            pixel: Pixel::YUVJ420P,
            space,
            range: Range::JPEG,
        });
    }
    // Untagged range is treated as limited by FFmpeg; YUVJ implies full.
    cases.push(Case {
        pixel: Pixel::YUV420P,
        space: Space::BT709,
        range: Range::Unspecified,
    });
    cases.push(Case {
        pixel: Pixel::YUVJ420P,
        space: Space::BT709,
        range: Range::Unspecified,
    });
    cases
}

/// Mid-grey luma with strong positive Cr: the decoded red differs by
/// roughly 0.05 between BT.601 and BT.709, i.e. ~8 output codes at 8 bits.
fn source_codes(f: &Format, full: bool) -> [u16; 3] {
    encode(f.bits, full, 0.45, -0.05, 0.30).map(|v| v.round() as u16)
}

#[test]
fn lut_input_matrix_and_range_follow_frame_tags_for_every_camera_format() {
    let cube = gray_from_red_cube();
    let mut worst = 0.0f64;
    let mut problems = Vec::new();
    for (brightness, contrast) in [(0.0, 0.0), (0.06, -0.1)] {
        for case in matrix_cases() {
            let f = format(case.pixel);
            let full = full_range(case.pixel, case.range);
            let codes = source_codes(&f, full);
            let alpha = if f.alpha { 384 } else { 0 };
            let frame = uniform(case.pixel, case.space, case.range, codes, alpha);
            let mut lut = ExportLut::with_adjustments(Some(&cube), brightness, contrast).unwrap();
            let output = lut.apply(&frame).unwrap();
            let label = format!(
                "{:?} {:?} {:?} b{brightness} c{contrast}",
                case.pixel, case.space, case.range
            );
            // YUVJ implies full range; FFmpeg 9 resolves an unspecified range
            // on a YUVJ frame to JPEG on the way out (observed, harmless).
            let expected_range = if full && case.range == Range::Unspecified {
                Range::JPEG
            } else {
                frame.color_range()
            };
            assert_eq!(
                (
                    output.format(),
                    output.width(),
                    output.height(),
                    output.pts(),
                    output.color_space(),
                    output.color_range(),
                    output.aspect_ratio()
                ),
                (
                    frame.format(),
                    frame.width(),
                    frame.height(),
                    frame.pts(),
                    frame.color_space(),
                    expected_range,
                    frame.aspect_ratio()
                ),
                "{label}: format and tags must be preserved"
            );
            let red = decode_red(f.bits, full, codes.map(f64::from), case.space).clamp(0.0, 1.0);
            let gray = grade(OFFSET + GAIN * red, brightness, contrast);
            let expected = encode(f.bits, full, gray, 0.0, 0.0);
            let ranges = component_ranges(&output);
            for (c, name) in ["Y", "Cb", "Cr"].iter().enumerate() {
                let (lo, hi) = ranges[c];
                worst = worst.max(
                    (lo as f64 - expected[c])
                        .abs()
                        .max((hi as f64 - expected[c]).abs())
                        / (1u32 << (f.bits - 8)) as f64,
                );
                problems.extend(mismatch(
                    &label,
                    name,
                    ranges[c],
                    expected[c],
                    tolerance(f.bits),
                ));
            }
            if f.alpha {
                assert_eq!(ranges[3], (alpha, alpha), "{label}: alpha must be exact");
            }
        }
    }
    eprintln!("LUT input matrix/range matrix: worst {worst:.2} 8-bit-equivalent codes");
    report("input matrix", problems);
}

#[test]
fn lut_output_is_encoded_with_the_frame_matrix_and_range() {
    let cube = constant_cube();
    let mut worst = 0.0f64;
    let mut problems = Vec::new();
    for (brightness, contrast) in [(0.0, 0.0), (0.06, -0.1)] {
        for case in matrix_cases() {
            let f = format(case.pixel);
            let full = full_range(case.pixel, case.range);
            let frame = uniform(
                case.pixel,
                case.space,
                case.range,
                source_codes(&f, full),
                1023,
            );
            let output = ExportLut::with_adjustments(Some(&cube), brightness, contrast)
                .unwrap()
                .apply(&frame)
                .unwrap();
            let label = format!(
                "{:?} {:?} {:?} b{brightness} c{contrast}",
                case.pixel, case.space, case.range
            );
            let rgb = CONSTANT.map(|v| grade(v, brightness, contrast));
            let (y, pb, pr) = rgb_to_ypbpr(rgb, case.space);
            let expected = encode(f.bits, full, y, pb, pr);
            let ranges = component_ranges(&output);
            for (c, name) in ["Y", "Cb", "Cr"].iter().enumerate() {
                let (lo, hi) = ranges[c];
                worst = worst.max(
                    (lo as f64 - expected[c])
                        .abs()
                        .max((hi as f64 - expected[c]).abs())
                        / (1u32 << (f.bits - 8)) as f64,
                );
                problems.extend(mismatch(
                    &label,
                    name,
                    ranges[c],
                    expected[c],
                    tolerance(f.bits),
                ));
            }
        }
    }
    eprintln!("LUT output matrix/range matrix: worst {worst:.2} 8-bit-equivalent codes");
    report("output matrix", problems);
}

#[test]
fn limited_range_super_white_and_sub_black_are_clamped_to_the_lut_domain() {
    // Action cameras commonly record limited-range luma outside 16..235.
    // A .cube LUT has a 0..1 domain, so those excursions are clipped before
    // the LUT; the export never extrapolates past the table.
    let cube = gray_from_red_cube();
    for pixel in [Pixel::YUV420P, Pixel::YUV420P10LE, Pixel::P010LE] {
        let f = format(pixel);
        let scale = 1u16 << (f.bits - 8);
        for (luma, red) in [(254u16, 1.0), (1u16, 0.0)] {
            let codes = [luma * scale, 128 * scale, 128 * scale];
            let frame = uniform(pixel, Space::BT709, Range::MPEG, codes, 0);
            let output = ExportLut::new(&cube).unwrap().apply(&frame).unwrap();
            let expected = encode(f.bits, false, OFFSET + GAIN * red, 0.0, 0.0);
            assert_close(
                &format!("{pixel:?} luma {luma}"),
                "Y",
                component_ranges(&output)[0],
                expected[0],
                tolerance(f.bits),
            );
        }
    }
}

#[test]
fn rgb_export_targets_apply_the_lut_once_without_a_matrix() {
    // PNG/EXR exports reach the LUT as RGB after encoder conversion.
    // The LUT stage itself must not apply any further YCbCr matrix.
    ffmpeg_next::init().unwrap();
    let cube = gray_from_red_cube();
    for (pixel, max, bytes, big_endian) in [
        (Pixel::RGB24, 255.0f64, 1usize, false),
        (Pixel::RGB48BE, 65535.0, 2, true),
        (Pixel::RGBA64BE, 65535.0, 2, true),
    ] {
        let channels = if pixel == Pixel::RGBA64BE { 4 } else { 3 };
        let mut frame = Video::new(pixel, 6, 4);
        frame.set_color_space(Space::Unspecified);
        let values: [f64; 4] = [0.6, 0.2, 0.9, 0.5];
        for y in 0..4 {
            let stride = frame.stride(0);
            for x in 0..6 {
                for c in 0..channels {
                    let v = (values[c] * max).round() as u16;
                    let off = y * stride + (x * channels + c) * bytes;
                    if bytes == 1 {
                        frame.data_mut(0)[off] = v as u8;
                    } else if big_endian {
                        frame.data_mut(0)[off..][..2].copy_from_slice(&v.to_be_bytes());
                    }
                }
            }
        }
        let output = ExportLut::new(&cube).unwrap().apply(&frame).unwrap();
        assert_eq!(output.format(), pixel);
        let mut worst = 0.0f64;
        let expected = (OFFSET + GAIN * 0.6) * max;
        // 16-bit RGB passes libswscale's integer path into float; measured
        // error is ~2^-12 of full scale, so 16-bit output is not bit-exact.
        let tol = if bytes == 1 { 1.0 } else { 32.0 };
        for y in 0..4 {
            for x in 0..6 {
                for c in 0..channels {
                    let off = y * output.stride(0) + (x * channels + c) * bytes;
                    let v = if bytes == 1 {
                        output.data(0)[off] as f64
                    } else {
                        u16::from_be_bytes(output.data(0)[off..][..2].try_into().unwrap()) as f64
                    };
                    let want = if c == 3 {
                        (0.5 * max).round()
                    } else {
                        expected
                    };
                    worst = worst.max((v - want).abs());
                    assert!(
                        (v - want).abs() <= tol,
                        "{pixel:?} channel {c}: {v} != {want}"
                    );
                }
            }
        }
        eprintln!("{pixel:?}: worst {worst} codes");
    }
}

fn encoder_rgb(frame: &Video, pixel: Pixel, color_active: bool) -> Video {
    encoder_rgb_with(frame, pixel, |context, rgb| {
        crate::ffmpeg_encoder_color::configure(context, frame, rgb, color_active).unwrap();
    })
}

fn encoder_rgb_with(
    frame: &Video,
    pixel: Pixel,
    configure: impl FnOnce(&mut ffmpeg_next::software::scaling::Context, &Video),
) -> Video {
    use ffmpeg_next::{ffi, software::scaling};
    let mut rgb = Video::new(pixel, frame.width(), frame.height());
    // Defined synthetic padding, including the float vectors used by lut3d.
    for plane in 0..rgb.planes() {
        rgb.data_mut(plane).fill(0);
    }
    assert_eq!(
        unsafe { ffi::av_frame_copy_props(rgb.as_mut_ptr(), frame.as_ptr()) },
        0
    );
    let mut context = scaling::Context::get(
        frame.format(),
        frame.width(),
        frame.height(),
        pixel,
        frame.width(),
        frame.height(),
        scaling::Flags::BILINEAR,
    )
    .unwrap();
    configure(&mut context, &rgb);
    context.run(frame, &mut rgb).unwrap();
    rgb
}

fn rgb_red(frame: &Video) -> f64 {
    match frame.format() {
        Pixel::RGB24 => frame.data(0)[0] as f64 / 255.0,
        Pixel::RGB48BE => {
            u16::from_be_bytes(frame.data(0)[..2].try_into().unwrap()) as f64 / 65535.0
        }
        Pixel::GBRPF32LE => f32::from_le_bytes(frame.data(2)[..4].try_into().unwrap()) as f64,
        other => panic!("unexpected RGB fixture {other:?}"),
    }
}

#[test]
fn encoder_rgb_and_yuv_lut_inputs_agree_for_explicit_sdr_tags() {
    let cube = gray_from_red_cube();
    let mut problems = Vec::new();
    for space in [
        Space::BT709,
        Space::SMPTE170M,
        Space::BT470BG,
        Space::BT2020NCL,
    ] {
        for range in [Range::MPEG, Range::JPEG] {
            for pixel in [
                Pixel::YUV420P,
                Pixel::YUV420P10LE,
                Pixel::P010LE,
                Pixel::NV12,
                Pixel::YUVJ420P,
                Pixel::YUV422P10LE,
            ] {
                let f = format(pixel);
                let full = full_range(pixel, range);
                let codes = source_codes(&f, full);
                let frame = uniform(pixel, space, range, codes, 0);
                let expected = OFFSET
                    + GAIN
                        * decode_red(f.bits, full, codes.map(|x| x as f64), space).clamp(0.0, 1.0);
                let yuv = ExportLut::new(&cube).unwrap().apply(&frame).unwrap();
                let yuv_gray = if full {
                    component_ranges(&yuv)[0].0 as f64 / ((1u32 << f.bits) - 1) as f64
                } else {
                    (component_ranges(&yuv)[0].0 as f64 / (1u32 << (f.bits - 8)) as f64 - 16.0)
                        / 219.0
                };
                for target in [Pixel::RGB24, Pixel::RGB48BE, Pixel::GBRPF32LE] {
                    let rgb = encoder_rgb(&frame, target, true);
                    assert_eq!(
                        (rgb.pts(), rgb.aspect_ratio()),
                        (frame.pts(), frame.aspect_ratio())
                    );
                    let output = ExportLut::new(&cube).unwrap().apply(&rgb).unwrap();
                    let gray = rgb_red(&output);
                    if (gray - expected).abs() > 2.0 / 255.0
                        || (gray - yuv_gray).abs() > 2.5 / 219.0
                    {
                        problems.push(format!("{pixel:?} {space:?} {range:?} -> {target:?}: gray {gray:.5}, expected {expected:.5}, YUV {yuv_gray:.5}"));
                    }
                }
            }
        }
    }
    report("production encoder RGB LUT input", problems);
}

#[test]
fn encoder_neutral_and_unknown_tag_conversion_keep_the_legacy_policy() {
    let f = format(Pixel::YUV420P);
    let codes = source_codes(&f, false);
    for space in [
        Space::BT709,
        Space::SMPTE170M,
        Space::BT2020NCL,
        Space::Unspecified,
    ] {
        let frame = uniform(Pixel::YUV420P, space, Range::MPEG, codes, 0);
        let rgb = encoder_rgb(&frame, Pixel::RGB24, false);
        // Frozen pre-fix configuration from ffmpeg_video.rs at71c22db0.
        // This compares neutral bytes with the existing library invocation;
        // the colored-path test above uses independent YCbCr equations.
        let legacy = encoder_rgb_with(&frame, Pixel::RGB24, |context, target| unsafe {
            let coefficients =
                ffmpeg_next::ffi::sws_getCoefficients(ffmpeg_next::ffi::SWS_CS_ITU709);
            assert_eq!(
                ffmpeg_next::ffi::sws_setColorspaceDetails(
                    context.as_mut_ptr(),
                    coefficients,
                    i32::from(frame.color_range() == Range::JPEG),
                    coefficients,
                    i32::from(target.color_range() == Range::JPEG),
                    0,
                    1 << 16,
                    1 << 16,
                ),
                0
            );
        });
        for y in 0..rgb.height() as usize {
            assert_eq!(
                &rgb.data(0)[y * rgb.stride(0)..][..rgb.width() as usize * 3],
                &legacy.data(0)[y * legacy.stride(0)..][..legacy.width() as usize * 3]
            );
        }
        if space == Space::Unspecified {
            let active = encoder_rgb(&frame, Pixel::RGB24, true);
            for y in 0..rgb.height() as usize {
                assert_eq!(
                    &active.data(0)[y * active.stride(0)..][..active.width() as usize * 3],
                    &rgb.data(0)[y * rgb.stride(0)..][..rgb.width() as usize * 3]
                );
            }
        }
    }
}

#[test]
fn active_yuv_encoder_keeps_its_initial_conversion_configuration() {
    use ffmpeg_next::{ffi, software::scaling};
    let frame = uniform(Pixel::YUV420P, Space::BT709, Range::MPEG, [100, 90, 180], 0);
    let target = Video::new(Pixel::YUV420P10LE, frame.width(), frame.height());
    let mut context = scaling::Context::get(
        frame.format(),
        frame.width(),
        frame.height(),
        target.format(),
        target.width(),
        target.height(),
        scaling::Flags::BILINEAR,
    )
    .unwrap();
    crate::ffmpeg_encoder_color::configure(&mut context, &frame, &target, false).unwrap();
    fn configuration(context: &mut scaling::Context) -> ([i32; 4], [i32; 4], [i32; 5]) {
        let (mut inverse, mut table) = (std::ptr::null_mut(), std::ptr::null_mut());
        let (mut src, mut dst, mut brightness, mut contrast, mut saturation) = (0, 0, 0, 0, 0);
        unsafe {
            assert_eq!(
                ffi::sws_getColorspaceDetails(
                    context.as_mut_ptr(),
                    &mut inverse,
                    &mut src,
                    &mut table,
                    &mut dst,
                    &mut brightness,
                    &mut contrast,
                    &mut saturation
                ),
                0
            );
            (
                std::slice::from_raw_parts(inverse, 4).try_into().unwrap(),
                std::slice::from_raw_parts(table, 4).try_into().unwrap(),
                [src, dst, brightness, contrast, saturation],
            )
        }
    }
    let initial = configuration(&mut context);
    let changed = uniform(
        Pixel::YUV420P,
        Space::BT2020NCL,
        Range::JPEG,
        [100, 90, 180],
        0,
    );
    crate::ffmpeg_encoder_color::configure(&mut context, &changed, &target, true).unwrap();
    assert_eq!(configuration(&mut context), initial);
}

#[test]
fn reused_rgb_encoder_honors_changed_source_matrix_and_range() {
    use ffmpeg_next::software::scaling;
    let first = uniform(
        Pixel::YUV420P,
        Space::SMPTE170M,
        Range::MPEG,
        [100, 90, 180],
        0,
    );
    let next = uniform(
        Pixel::YUV420P,
        Space::BT2020NCL,
        Range::JPEG,
        [100, 90, 180],
        0,
    );
    let mut output = Video::new(Pixel::RGB24, first.width(), first.height());
    let mut context = scaling::Context::get(
        first.format(),
        first.width(),
        first.height(),
        output.format(),
        output.width(),
        output.height(),
        scaling::Flags::BILINEAR,
    )
    .unwrap();
    for source in [&first, &next, &first] {
        crate::ffmpeg_encoder_color::configure(&mut context, source, &output, true).unwrap();
        context.run(source, &mut output).unwrap();
        let fresh = encoder_rgb(source, Pixel::RGB24, true);
        for y in 0..output.height() as usize {
            assert_eq!(
                &output.data(0)[y * output.stride(0)..][..output.width() as usize * 3],
                &fresh.data(0)[y * fresh.stride(0)..][..fresh.width() as usize * 3]
            );
        }
    }
}

#[test]
fn single_lut_application_with_and_without_adjustments() {
    // The adjusted path splits into an RGB graph and an output graph built
    // with apply_lut=false (export_lut.rs:307,320). A second application of
    // this non-idempotent LUT would move gray by GAIN*gray+OFFSET again.
    let cube = gray_from_red_cube();
    let f = format(Pixel::YUV420P10LE);
    let codes = encode(10, false, 0.5, 0.0, 0.0).map(|v| v.round() as u16);
    for (brightness, contrast) in [(0.0, 0.0), (0.05, 0.0), (0.0, 0.2)] {
        let frame = uniform(Pixel::YUV420P10LE, Space::BT709, Range::MPEG, codes, 0);
        let output = ExportLut::with_adjustments(Some(&cube), brightness, contrast)
            .unwrap()
            .apply(&frame)
            .unwrap();
        let once = grade(OFFSET + GAIN * 0.5, brightness, contrast);
        let twice = grade(OFFSET + GAIN * (OFFSET + GAIN * 0.5), brightness, contrast);
        let expected_once = encode(10, false, once, 0.0, 0.0)[0];
        let expected_twice = encode(10, false, twice, 0.0, 0.0)[0];
        assert!((expected_once - expected_twice).abs() > 3.0 * tolerance(f.bits));
        assert_close(
            &format!("b{brightness} c{contrast}"),
            "Y",
            component_ranges(&output)[0],
            expected_once,
            tolerance(f.bits),
        );
    }
}

#[test]
fn neutral_controls_without_lut_need_no_export_stage() {
    // mod.rs:282 builds no ExportLut when the URL is empty and all eight
    // controls are zero; ExportLut itself must also be an identity if built.
    let codes = encode(10, false, 0.45, -0.05, 0.30).map(|v| v.round() as u16);
    for pixel in [Pixel::YUV420P10LE, Pixel::P010LE] {
        let frame = uniform(pixel, Space::BT709, Range::MPEG, codes, 0);
        let output = ExportLut::with_adjustments(None, 0.0, 0.0)
            .unwrap()
            .apply(&frame)
            .unwrap();
        assert_eq!(
            component_ranges(&output),
            component_ranges(&frame),
            "{pixel:?}"
        );
    }
}

mod cube_parser {
    use super::CubeLut;

    fn lattice(size: usize) -> String {
        let mut text = format!("LUT_3D_SIZE {size}\n");
        let d = (size - 1) as f32;
        for b in 0..size {
            for g in 0..size {
                for r in 0..size {
                    text.push_str(&format!(
                        "{} {} {}\n",
                        r as f32 / d,
                        g as f32 / d,
                        b as f32 / d
                    ));
                }
            }
        }
        text
    }

    #[test]
    fn bom_crlf_tabs_comments_and_decimal_domain_parse_identically() {
        let plain = CubeLut::parse(lattice(3).as_bytes()).unwrap();
        let decorated = format!(
            "\u{feff}# Vendor LUT\r\nTITLE \"Camera # to Rec.709\"\r\nDOMAIN_MIN 0.0 0.0 0.0\r\nDOMAIN_MAX 1.0 1.0 1.0\r\n{}",
            lattice(3).replace(' ', "\t").replace('\n', "\r\n")
        );
        let parsed = CubeLut::parse(decorated.as_bytes()).unwrap();
        assert_eq!(parsed.size, plain.size);
        assert_eq!(parsed.entries, plain.entries);
    }

    #[test]
    fn canonical_snapshot_round_trips_every_float_bit() {
        // The export and preview both re-parse the canonical text written by
        // canonical_cube(); awkward values must survive bit-exactly.
        let awkward = [
            0.1f32,
            1.0 / 3.0,
            1e-7,
            0.999_999_94,
            0.5,
            1.0,
            0.0,
            2.0f32.powi(-20),
        ];
        let mut text = String::from("LUT_3D_SIZE 2\n");
        for i in 0..8 {
            let v = awkward[i];
            text.push_str(&format!(
                "{:e} {} {:.9}\n",
                v,
                awkward[(i + 3) % 8],
                awkward[(i + 5) % 8]
            ));
        }
        let lut = CubeLut::parse(text.as_bytes()).unwrap();
        let again = CubeLut::parse(&lut.canonical_cube()).unwrap();
        for (a, b) in lut.entries.iter().zip(&again.entries) {
            for c in 0..3 {
                assert_eq!(a[c].to_bits(), b[c].to_bits());
            }
        }
    }

    #[test]
    fn common_vendor_sizes_are_accepted_and_bounds_rejected() {
        for size in [2, 17, 33, 65] {
            assert_eq!(CubeLut::parse(lattice(size).as_bytes()).unwrap().size, size);
        }
        assert!(CubeLut::parse(b"LUT_3D_SIZE 1\n0 0 0\n").is_err());
        assert!(CubeLut::parse(b"LUT_3D_SIZE 129\n").is_err());
    }

    #[test]
    fn domain_extra_missing_and_case_errors_fail_closed() {
        let base = lattice(2);
        let cases: Vec<(&str, String)> = vec![
            ("domain below zero", format!("DOMAIN_MIN -0.1 0 0\n{base}")),
            ("log domain", format!("DOMAIN_MAX 1 1 1.5\n{base}")),
            ("extra entry", format!("{base}0 0 0\n")),
            (
                "missing entry",
                base.lines().take(8).collect::<Vec<_>>().join("\n"),
            ),
            (
                "lowercase keyword",
                base.replace("LUT_3D_SIZE", "lut_3d_size"),
            ),
            ("1D LUT", "LUT_1D_SIZE 2\n0 0 0\n1 1 1\n".into()),
            (
                "shaper range before size",
                format!("LUT_3D_INPUT_RANGE 0 1\n{base}"),
            ),
            (
                "shaper range after size",
                base.replacen("\n", "\nLUT_3D_INPUT_RANGE 0 1\n", 1),
            ),
            ("non-finite", base.replacen("0 0 0", "nan 0 0", 1)),
        ];
        for (name, text) in cases {
            let result = CubeLut::parse(text.as_bytes());
            assert!(result.is_err(), "{name} must be rejected");
            eprintln!("{name}: {}", result.err().unwrap());
        }
    }
}
