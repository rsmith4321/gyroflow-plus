// SPDX-License-Identifier: GPL-3.0-or-later
//! Production float-frame / preview-texture fixture, for independent OCIO checks.
use ffmpeg_next::{format::Pixel, frame::Video};
use gyroflow_export_lut_tests::{cube_lut::CubeLut, export_lut::ExportLut, tone_curve::ToneCurve};
use std::{error::Error, fs};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 11 && args.len() != 12 {
        return Err("tone_fixture input.rgba32f output.rgba32f tone.rgb w h brightness contrast shadows highlights copies [lut.cube]".into());
    }
    let (w, h): (usize, usize) = (args[4].parse()?, args[5].parse()?);
    let (b, c, s, hi) = (args[6].parse()?, args[7].parse()?, args[8].parse()?, args[9].parse()?);
    let input = fs::read(&args[1])?;
    if input.len() != w * h * 16 { return Err("Expected packed RGBA float32 LE".into()); }
    ffmpeg_next::init()?;
    let mut frame = Video::new(Pixel::GBRAPF32LE, w as u32, h as u32);
    frame.set_pts(Some(987654));
    for (plane, channel) in [1, 2, 0, 3].into_iter().enumerate() {
        let stride = frame.stride(plane);
        frame.data_mut(plane).fill(0x5a);
        for y in 0..h {
            for x in 0..w {
                let i = (y * w + x) * 16 + channel * 4;
                frame.data_mut(plane)[y * stride + x * 4..][..4].copy_from_slice(&input[i..i + 4]);
            }
        }
    }
    let original: Vec<Vec<u8>> = (0..4).map(|p| frame.data(p).to_vec()).collect();
    let lut = args.get(11).map(fs::read).transpose()?;
    if let Some(lut) = lut.as_ref() {
        let cube = CubeLut::parse(lut)?;
        let (width, height, data) = cube.atlas();
        let folder = std::path::Path::new(&args[3]).parent().unwrap();
        fs::write(folder.join("atlas.rgb"), data)?;
        fs::write(folder.join("atlas-size.txt"), format!("{width} {height} {}", cube.size))?;
    }
    let mut filter = ExportLut::with_color(lut.as_deref(), b, c, s, hi)?;
    let mut pixels = Vec::with_capacity(input.len());
    for _ in 0..args[10].parse::<usize>()? {
        let output = filter.apply(&frame)?;
        assert_eq!(output.pts(), Some(987654));
        assert_eq!(output.format(), Pixel::GBRAPF32LE);
        for (p, saved) in original.iter().enumerate() {
            assert!(frame.data(p) == saved, "Input plane {p} was mutated");
        }
        pixels.clear();
        for y in 0..h {
            for x in 0..w {
                for plane in [2, 0, 1, 3] {
                    pixels.extend_from_slice(&output.data(plane)[y * output.stride(plane) + x * 4..][..4]);
                }
            }
        }
    }
    fs::write(&args[2], pixels)?;
    if let Some(curve) = ToneCurve::new(s, hi)? { fs::write(&args[3], curve.texture_bytes())?; }
    Ok(())
}
