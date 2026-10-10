// SPDX-License-Identifier: GPL-3.0-or-later
//! Configure the encoder-target converter; all conversion math stays in FFmpeg.
use ffmpeg_next::{
    Error,
    color::{Range, Space},
    ffi,
    format::Pixel,
    frame::Video,
    software::scaling::Context,
};

pub fn configure(
    context: &mut Context,
    source: &Video,
    target: &Video,
    color_active: bool,
) -> Result<(), Error> {
    let descriptor = unsafe { ffi::av_pix_fmt_desc_get(target.format().into()) };
    let rgb_target = !descriptor.is_null()
        && unsafe { (*descriptor).flags & ffi::AV_PIX_FMT_FLAG_RGB as u64 != 0 };
    if color_active && !rgb_target {
        // The video/YUV converter was configured once at creation. Avoid
        // reconfiguring it per frame on the hardware-encoder path.
        return Ok(());
    }
    // The upstream converter forces BT.709. For color-active RGB delivery,
    // honor explicit source matrix tags as the YUV ExportLut path does, so
    // choosing PNG/EXR does not change the RGB presented to the processor.
    // Keep neutral exports, YUV targets and unknown matrix policy unchanged.
    let matrix = if color_active && rgb_target {
        match source.color_space() {
            Space::BT709 => ffi::SWS_CS_ITU709,
            Space::BT470BG | Space::SMPTE170M => ffi::SWS_CS_ITU601,
            Space::BT2020NCL => ffi::SWS_CS_BT2020,
            _ => ffi::SWS_CS_ITU709,
        }
    } else {
        ffi::SWS_CS_ITU709
    };
    // libswscale treats YUVJ pixel formats as full range even when the
    // separate frame range tag is absent or contradicts the pixel format.
    // Preserve that convention for the color-active RGB path only.
    let jpeg_format = matches!(
        source.format(),
        Pixel::YUVJ420P | Pixel::YUVJ411P | Pixel::YUVJ422P | Pixel::YUVJ444P | Pixel::YUVJ440P
    );
    let src_range = i32::from(
        source.color_range() == Range::JPEG || (color_active && rgb_target && jpeg_format),
    );
    let dst_range = i32::from(target.color_range() == Range::JPEG);
    let code = unsafe {
        let coefficients = ffi::sws_getCoefficients(matrix);
        ffi::sws_setColorspaceDetails(
            context.as_mut_ptr(),
            coefficients,
            src_range,
            coefficients,
            dst_range,
            0,
            1 << 16,
            1 << 16,
        )
    };
    // Legacy initialization ignores this status; retain that behavior for
    // neutral/YUV exports, but never process colors with a rejected RGB setup.
    if color_active && code < 0 {
        Err(Error::from(code))
    } else {
        Ok(())
    }
}
