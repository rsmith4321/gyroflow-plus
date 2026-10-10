# Independent review of the color prototype

Reviewed 2026-10-07 against application prototype `48231d21` and the combined
preview/reference verification in `a0405899`. The review covered the export
filter, sampled curve and provenance, shader texture packing and alpha handling,
processing order, neutral bypass, errors, project/preset/queue persistence,
export markers, application/settings/update identities, staging and notices.

## Findings fixed

1. **Incomplete development source snapshots.** Development staging previously
   permitted a dirty checkout, then archived HEAD and saved a tracked-file diff.
   Newly added, untracked source was omitted from both. A disposable packaging
   fixture reproduced this. All staging now requires committed source, including
   development runtimes. This avoids silently omitting source or archiving
   private untracked files. Dirty-source patch generation was removed.
2. **False external dependencies for universal Mac binaries.** The dependency
   audit treated later architecture-header filenames from `otool -L` as library
   dependencies. It now reads only indented versioned dependency records and
   still reports genuine absolute non-system libraries. A synthetic universal
   output fixture verifies that architecture headers are excluded.

Both focused packaging tests pass with Python's standard-library unittest.
These fixes do not change the compiled color/rendering paths or their timing.

## Evidence accepted, with limits

- The 16 parser/filter/curve tests include the earlier ownership, alpha,
  ten-bit, stride, color-property and neutral-path checks.
- The independent OpenColorIO CPU comparison and production Metal shader
  comparisons are documented in [the prototype report](COLOR-TONE-PROTOTYPE.md).
  The bounded sampled curve is an approximation, not the full OCIO runtime.
- For the tested moving section, all 481 neutral frames and timestamps match
  the earlier export. Color output differs by at most one ten-bit value from
  the independent reference. This does not establish equivalence for every
  codec, color space or recording.
- The one-second 4K measurements show modest added tone overhead, with the
  hardware-encoding option retained. They are not a full-flight speed guarantee.
- Original recording and official-app preservation checks passed. Separate
  settings and update identities prevent the fork from updating official
  Gyroflow or using its Store/WinGet release automation.

3. **Pre-signing hash mistaken for packaged executable hash.** The old build
   manifest used `binary_sha256` for its input executable. Ad-hoc Mac signing
   changes those bytes. It now calls this `input_binary_sha256` and writes the
   final `packaged_binary_sha256` in `PACKAGE.json` outside the signed bundle,
   avoiding a circular resource hash. Actual Mac development staging verifies
   that final receipt matches the executable and deep/strict signature passes.

## Native acceptance and remaining release gates

The initial file-open stall cleared; the cause remains unconfirmed. Resumed
native testing verified playback, embedded motion detection, four double-click
reset gestures, reset-all, preview comparison, GUI project saving and reopening
after restart. The separately installed local development app completed a native
queue export with all 481 frames decoded and the selected LUT/tone values in
its output metadata. See [the acceptance report](COLOR-TONE-PROTOTYPE.md).

The installed build is a machine-specific development app, not a portable
public release. Windows runtime validation of the new controls and portable
package licensing, dependency closure, clean-machine and signing checks remain
open. The next requested broader basic grading controls are not implemented
by this acceptance milestone.

## Expanded basic grade review (2026-10-07)

The expanded candidate was reviewed for neutral compatibility, relative versus
RAW white balance, exposure transfer/order, f64/f32 roundoff, saturation plane
ownership, alpha/padding, invalid parameters, queue/preset fields, reset and
comparison behavior, shader bindings and backend variants, and claimed
processing headroom. The implementation preserves the older bounded stages
and documents their limits rather than silently changing old projects.

New saturation code obtains live FFmpeg plane pointers only after making the
frame writable. Before creating simultaneous mutable float slices it checks
stride, height, overflow, alignment and nonoverlapping memory ranges. Rayon
zips rows, edits only the active RGB width, and leaves alpha untouched. Repeated
shared-frame tests and independent float/Metal/moving-footage checks pass.

The independent reference initially used OCIO's default fast-power optimization,
which differed by 1.37e−5 for fractional exposure. Using OCIO's unoptimized
exponent/linear-primary/inverse-exponent chain isolates the specified math:
maximum native deviation is 4.77e−7. This is a reference precision correction;
production computes channel gains once and applies a multiply per sample.

Native UI acceptance, installation and final timing are recorded in the
[basic grading report](BASIC-GRADING-PLAN.md). Portable distribution and Windows
runtime validation remain open until tested on those environments.

### Native preview issue found and fixed

The native visual check found the player rendering a 32×32 placeholder even
with grading bypassed and Full/1080p selected. The surface-size setter updated
its requested dimensions but did not request a scene-graph node update.
Controller now explicitly schedules `QQuickItem::update()` after changing the
preview surface. In the rebuilt candidate a 1920×1080 player texture was confirmed;
restoring Full preview visibly processes 3840×2160 and the native footage is sharp. Export processing is unchanged.

Opening the first project also returned macOS `Operation not permitted` for
its externally referenced recording. Selecting the original through the normal
file picker provided access; the GUI-saved project reopened on the next build.
No macOS security protections or internal permission databases were changed.

The expanded acceptance passed actual GUI save/restart, comparison, reset and
queue export. The queue's 481 decoded frame hashes and timestamps exactly
match the CLI export. The installed executable matches the staged signed
binary. No unresolved defect was found in the reviewed expanded path; the
listed platform, color-management and portable packaging limits remain open.
