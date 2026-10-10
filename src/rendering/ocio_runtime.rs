// SPDX-License-Identifier: GPL-3.0-or-later
//! Validated bridge to pinned official OCIO. No image color algorithms here.
use ffmpeg_next::{ffi, format::Pixel, frame::Video};
use rayon::prelude::*;
use std::{
    ffi::{CStr, CString, c_char, c_void},
    ptr::NonNull,
};

#[derive(Clone, Copy, Default)]
pub struct Settings {
    pub brightness: f64,
    pub contrast: f64,
    pub shadows: f64,
    pub highlights: f64,
    pub exposure: f64,
    pub saturation: f64,
    pub warmth: f64,
    pub tint: f64,
}
impl Settings {
    fn values(self) -> [f64; 8] {
        [
            self.brightness,
            self.contrast,
            self.shadows,
            self.highlights,
            self.exposure,
            self.saturation,
            self.warmth,
            self.tint,
        ]
    }
}

unsafe extern "C" {
    fn gp_ocio_create_with_lut(
        parameters: *const f64,
        path: *const c_char,
        error: *mut c_char,
        capacity: usize,
    ) -> *mut c_void;
    fn gp_ocio_destroy(processor: *mut c_void);
    fn gp_ocio_apply(
        processor: *const c_void,
        r: *mut f32,
        g: *mut f32,
        b: *mut f32,
        width: u32,
        height: u32,
        r_stride: usize,
        g_stride: usize,
        b_stride: usize,
        error: *mut c_char,
        capacity: usize,
    ) -> i32;
    fn gp_ocio_texture3d(
        processor: *const c_void,
        output: *mut f32,
        float_capacity: usize,
        edge: *mut u32,
        error: *mut c_char,
        capacity: usize,
    ) -> usize;
    fn gp_ocio_shader(
        processor: *const c_void,
        output: *mut c_char,
        output_capacity: usize,
        error: *mut c_char,
        capacity: usize,
    ) -> usize;
}

pub struct Texture3D {
    pub edge: u32,
    pub values: Vec<f32>,
}
pub struct ShaderResources {
    pub text: String,
    pub texture: Option<Texture3D>,
}

pub struct OcioProcessor {
    handle: NonNull<c_void>,
    active: bool,
}
// The C++ snapshot holds only const processors, with no dynamic properties or
// parameter mutations. GPU descriptors are initialized once with std::call_once.
// Concurrent application reads their immutable operations;
// each call owns its image descriptor and disjoint output rows.
unsafe impl Send for OcioProcessor {}
unsafe impl Sync for OcioProcessor {}
impl Drop for OcioProcessor {
    fn drop(&mut self) {
        unsafe { gp_ocio_destroy(self.handle.as_ptr()) }
    }
}
fn error(buffer: &[c_char]) -> String {
    // C++ errors always terminate within the supplied initialized buffer.
    unsafe { CStr::from_ptr(buffer.as_ptr()) }
        .to_string_lossy()
        .into_owned()
}
impl OcioProcessor {
    pub fn new(settings: Settings) -> Result<Self, String> {
        Self::with_lut(settings, None)
    }
    /// The caller owns a bounded, validated canonical cube file. OCIO loads it
    /// during processor construction; pixel evaluation is entirely upstream.
    pub fn with_lut(settings: Settings, path: Option<&std::path::Path>) -> Result<Self, String> {
        let path = path
            .map(|p| {
                p.to_str()
                    .ok_or("LUT path is not UTF-8")
                    .and_then(|s| CString::new(s).map_err(|_| "LUT path contains a NUL"))
            })
            .transpose()?;
        let values = settings.values();
        let mut buffer = [0; 4096];
        let pointer = unsafe {
            gp_ocio_create_with_lut(
                values.as_ptr(),
                path.as_ref().map_or(std::ptr::null(), |p| p.as_ptr()),
                buffer.as_mut_ptr(),
                buffer.len(),
            )
        };
        Ok(Self {
            handle: NonNull::new(pointer).ok_or_else(|| error(&buffer))?,
            active: path.is_some() || values.iter().any(|x| *x != 0.0),
        })
    }
    pub fn is_active(&self) -> bool {
        self.active
    }
    pub fn shader_text(&self) -> Result<String, String> {
        let mut text = vec![0u8; 256 * 1024];
        let mut buffer = [0; 4096];
        let length = unsafe {
            gp_ocio_shader(
                self.handle.as_ptr(),
                text.as_mut_ptr().cast(),
                text.len(),
                buffer.as_mut_ptr(),
                buffer.len(),
            )
        };
        if length == 0 {
            return Err(error(&buffer));
        }
        if length > text.len() {
            return Err("Invalid OpenColorIO shader length".into());
        }
        text.truncate(length);
        String::from_utf8(text).map_err(|_| "Invalid OpenColorIO shader text".into())
    }
    pub fn gpu_resources(&self) -> Result<ShaderResources, String> {
        let text = self.shader_text()?;
        let mut edge = 0;
        let mut buffer = [0; 4096];
        let count = unsafe {
            gp_ocio_texture3d(
                self.handle.as_ptr(),
                std::ptr::null_mut(),
                0,
                &mut edge,
                buffer.as_mut_ptr(),
                buffer.len(),
            )
        };
        if buffer[0] != 0 {
            return Err(error(&buffer));
        }
        if count == 0 {
            return Ok(ShaderResources {
                text,
                texture: None,
            });
        }
        let expected = (edge as usize)
            .checked_pow(3)
            .and_then(|n| n.checked_mul(3));
        if !(2..=128).contains(&edge) || expected != Some(count) {
            return Err("Invalid OpenColorIO texture dimensions".into());
        }
        let mut values = vec![0.0; count];
        let copied = unsafe {
            gp_ocio_texture3d(
                self.handle.as_ptr(),
                values.as_mut_ptr(),
                values.len(),
                &mut edge,
                buffer.as_mut_ptr(),
                buffer.len(),
            )
        };
        if copied != count {
            return Err(error(&buffer));
        }
        if values.iter().any(|x| !x.is_finite()) {
            return Err("Invalid OpenColorIO texture values".into());
        }
        Ok(ShaderResources {
            text,
            texture: Some(Texture3D { edge, values }),
        })
    }
    pub fn apply_frame(&self, frame: &mut Video) -> Result<(), String> {
        if !matches!(frame.format(), Pixel::GBRPF32LE | Pixel::GBRAPF32LE)
            || cfg!(target_endian = "big")
        {
            return Err("OpenColorIO requires little-endian planar float RGB".into());
        }
        // Inspect signed strides and FFmpeg allocation ownership directly. The
        // ffmpeg-next slice helpers cast signed strides to usize, so they must
        // never be called on an unvalidated (e.g. vertically flipped) frame.
        let validate = |frame: &Video| -> Result<([usize; 3], [usize; 3], usize, usize), String> {
            let raw = unsafe { &*frame.as_ptr() };
            if raw.width <= 0 || raw.height <= 0 {
                return Err("Empty OpenColorIO frame".into());
            }
            let width = raw.width as usize;
            let height = raw.height as usize;
            let row_bytes = width.checked_mul(4).ok_or("OpenColorIO width overflow")?;
            let planes = if frame.format() == Pixel::GBRAPF32LE {
                4
            } else {
                3
            };
            let mut regions = Vec::with_capacity(planes);
            for plane in 0..planes {
                let stride = raw.linesize[plane];
                let pointer = raw.data[plane] as usize;
                if stride <= 0
                    || pointer == 0
                    || pointer % 4 != 0
                    || stride as usize % 4 != 0
                    || (stride as usize) < row_bytes
                {
                    return Err(
                        "Invalid OpenColorIO RGB plane layout (positive strides required)".into(),
                    );
                }
                let needed = (stride as usize)
                    .checked_mul(height - 1)
                    .and_then(|x| x.checked_add(row_bytes))
                    .ok_or("OpenColorIO height overflow")?;
                let end = pointer
                    .checked_add(needed)
                    .ok_or("OpenColorIO plane overflow")?;
                let owner = unsafe {
                    ffi::av_frame_get_plane_buffer(frame.as_ptr().cast_mut(), plane as i32)
                };
                if owner.is_null() {
                    return Err("OpenColorIO plane has no FFmpeg buffer owner".into());
                }
                let owner = unsafe { &*owner };
                let start = owner.data as usize;
                let limit = start
                    .checked_add(owner.size)
                    .ok_or("OpenColorIO buffer overflow")?;
                if start == 0 || pointer < start || end > limit {
                    return Err("OpenColorIO plane exceeds its FFmpeg buffer".into());
                }
                regions.push((pointer, end));
            }
            regions.sort_unstable();
            if regions.windows(2).any(|r| r[0].1 > r[1].0) {
                return Err("OpenColorIO planes overlap".into());
            }
            Ok((
                [
                    raw.linesize[2] as usize,
                    raw.linesize[0] as usize,
                    raw.linesize[1] as usize,
                ],
                [
                    raw.data[2] as usize,
                    raw.data[0] as usize,
                    raw.data[1] as usize,
                ],
                width,
                height,
            ))
        };
        validate(frame)?;
        let result = unsafe { ffi::av_frame_make_writable(frame.as_mut_ptr()) };
        if result < 0 {
            return Err(ffmpeg_next::Error::from(result).to_string());
        }
        let (strides, pointers, width, height) = validate(frame)?;
        let workers = rayon::current_num_threads().min(8).max(1);
        let rows = height.div_ceil(workers);
        (0..height.div_ceil(rows))
            .into_par_iter()
            .try_for_each(|band| {
                let y = band * rows;
                let count = (height - y).min(rows);
                let mut buffer = [0; 4096];
                // Every region was validated before spawning workers. Bands write
                // distinct rows in nonoverlapping FFmpeg-owned, writable planes.
                // Alpha and padding are excluded from the OCIO descriptor.
                let [r, g, b] =
                    std::array::from_fn::<_, 3, _>(|p| (pointers[p] + y * strides[p]) as *mut f32);
                let ok = unsafe {
                    gp_ocio_apply(
                        self.handle.as_ptr(),
                        r,
                        g,
                        b,
                        width as u32,
                        count as u32,
                        strides[0],
                        strides[1],
                        strides[2],
                        buffer.as_mut_ptr(),
                        buffer.len(),
                    )
                };
                if ok == 1 { Ok(()) } else { Err(error(&buffer)) }
            })
    }
}
