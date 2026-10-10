// SPDX-License-Identifier: GPL-3.0-or-later
//! Time the production export colour stage on synthetic frames.
//!
//! cargo run --release --example bench_export_color [--features ocio-runtime]
//! Environment: FRAMES (default 60), SIZE (default 3840x2160), RUNS (default 3;
//! the best run is reported, so a busy host inflates the numbers less).
use ffmpeg_next::{
    color::{Range, Space},
    format::Pixel,
    frame::Video,
};
use gyroflow_export_lut_tests::{basic_grade::BasicGradeSettings, export_lut::ExportLut};
use std::time::Instant;

fn cube(size: usize) -> Vec<u8> {
    let mut text = format!("LUT_3D_SIZE {size}\n");
    let curve = |v: usize| (v as f64 / (size - 1) as f64).powf(0.8);
    for b in 0..size {
        for g in 0..size {
            for r in 0..size {
                text.push_str(&format!("{:.6} {:.6} {:.6}\n", curve(r), curve(g) * 0.95, curve(b)));
            }
        }
    }
    text.into_bytes()
}

/// A tagged BT.709 limited-range frame with a gradient in every component.
fn source(pixel: Pixel, width: u32, height: u32) -> Video {
    let mut frame = Video::new(pixel, width, height);
    frame.set_color_space(Space::BT709);
    frame.set_color_range(Range::MPEG);
    for plane in 0..frame.planes() {
        let stride = frame.stride(plane);
        let data = frame.data_mut(plane);
        for (y, row) in data.chunks_exact_mut(stride).enumerate() {
            for (x, sample) in row.chunks_exact_mut(2).enumerate() {
                let code = 64 + ((x * 3 + y + plane * 97) % 876) as u16;
                // P010 keeps its 10 bits in the high end of each 16-bit word.
                let code = if pixel == Pixel::P010LE { code << 6 } else { code };
                sample.copy_from_slice(&code.to_le_bytes());
            }
        }
    }
    frame
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    ffmpeg_next::init()?;
    let env = |name: &str, default: usize| {
        std::env::var(name).ok().and_then(|v| v.parse().ok()).unwrap_or(default)
    };
    let (frames, runs) = (env("FRAMES", 60), env("RUNS", 3).max(1));
    let size = std::env::var("SIZE").unwrap_or_else(|_| "3840x2160".into());
    let (width, height) = size
        .split_once('x')
        .and_then(|(w, h)| Some((w.parse().ok()?, h.parse().ok()?)))
        .ok_or("SIZE must look like 3840x2160")?;
    let lut = cube(33);
    let grade = BasicGradeSettings { exposure: 0.3, saturation: 0.1, warmth: 0.05, tint: 0.0 };
    println!("{size}, {frames} frames, best of {runs} runs, {} Rayon threads",
             rayon::current_num_threads());
    for pixel in [Pixel::P010LE, Pixel::YUV420P10LE, Pixel::YUV422P10LE, Pixel::YUV420P] {
        let frame = source(pixel, width, height);
        for (name, bytes, settings) in [
            ("LUT", Some(&lut[..]), BasicGradeSettings::default()),
            ("LUT + grade", Some(&lut[..]), grade),
            ("grade only", None, grade),
        ] {
            let mut stage = ExportLut::with_grading(bytes, 0.05, 0.1, 0.0, 0.0, settings)?;
            stage.apply(&frame)?;
            let mut best = f64::MAX;
            for _ in 0..runs {
                let start = Instant::now();
                for _ in 0..frames {
                    std::hint::black_box(stage.apply(&frame)?);
                }
                best = best.min(start.elapsed().as_secs_f64() * 1000.0 / frames as f64);
            }
            println!("{:<12} {:<12} {best:6.2} ms/frame", format!("{pixel:?}"), name);
        }
    }
    Ok(())
}
