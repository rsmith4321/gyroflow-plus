# Enhanced Gyroflow spin-off

Working name: **Gyroflow Plus**, identified as a community fork. **ExtraFlow**
was the initial alternative. This is a development plan, not a released product
or a final public name. Ryan requested a separately maintained spin-off on
2026-10-07, with more color tools and an import-to-sharing workflow.

## Direction

- Retain Gyroflow's stabilization core and project compatibility.
- Maintain our own application identity, versioning and downloadable releases.
- Keep useful upstream improvements available for integration. Upstream is
  active: its latest default-branch commit on this check was
  `77b49409f6016d17e58e88d6a0914616bee6296e`, dated 2026-09-28. An old stable
  release is not evidence that development has stopped.
- Retain the GPLv3 license, original copyright/third-party notices, required
  acknowledgments and clear identification of modifications. Distribute the
  corresponding source alongside binaries. Preserve the focused upstream LUT
  pull request independently of fork branding and additional product features.
- Preserve original recordings and embedded motion data. Color settings affect
  preview and exported derivatives, with explicit markers for downstream tools.

## Existing foundation

User-selected `.cube` LUTs, recent LUTs, brightness/contrast, comparison preview,
reset gestures and saved project/preset/queue settings are implemented. The
native export adjustment optimization is now installed and tested on Mac:
see [COLOR-PERFORMANCE.md](COLOR-PERFORMANCE.md). Easy Eject already recognizes
the explicit exported-LUT marker to avoid applying that conversion twice.

## Color prototype

The implemented prototype evaluates [OpenColorIO's GradingToneTransform](https://opencolorio.readthedocs.io/en/v2.4.2/api/grading_transforms.html)
for post-LUT shadows/highlights. It offers tonal ranges and video/linear/log
styles; [primary grading and exposure transforms](https://opencolorio.readthedocs.io/en/stable/api/transforms.html)
also provide exposure and pivoted contrast. This is a better functional match
than assuming a hardware codec implements photographic adjustments.

The prototype must demonstrate consistent CPU export and Qt GPU preview,
neutral backward compatibility, explicit processing order, smooth tonal
transitions, alpha/ten-bit/frame ownership preservation, no frame-dependent
automatic changes, and acceptable measured 4K performance. Test a real moving
clip, independent references and the installed UI before publishing new controls.
Retain the verified fast build until the prototype meets those checks.

## Release work still open

- Final name/application branding, icon and public release acceptance.
- Independent app/settings/updater identities and safe staging are implemented;
  portable packaging, Windows installation and final branding remain open.
  See [PLUS-DISTRIBUTION.md](PLUS-DISTRIBUTION.md).
- Windows runtime validation of the latest native export optimization.
- Portable dependency packaging, signing/notarization as appropriate, reproducible
  release builds and actual install/export checks on both platforms.
- Native acceptance of the richer color controls and further import/sharing
  integration. A cached OpenColorIO-derived video-tone prototype and Highlights/Shadows
  controls are implemented; see [COLOR-TONE-PROTOTYPE.md](COLOR-TONE-PROTOTYPE.md).
  The native OCIO runtime is not integrated.

Easy Eject and ShootCal remain separate repositories. Their integration can use
documented links, file/folder handoff and explicit export markers without
including unrelated changes in the stabilization app or upstream PR.
