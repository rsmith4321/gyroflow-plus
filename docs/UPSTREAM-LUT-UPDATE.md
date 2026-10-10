# Upstream LUT discussion follow-up

Ryan authorized an update to [Gyroflow issue #250](https://github.com/gyroflow/gyroflow/issues/250) once a usable app download is ready. He also authorized closing [the earlier PR #1249](https://github.com/gyroflow/gyroflow/pull/1249) with an explanation. Preserve its code and discussion.

PR #1249 was closed, unmerged, on October 10, 2026 UTC. The [explanation](https://github.com/gyroflow/gyroflow/pull/1249#issuecomment-6092087028) is posted; its head remains `0e4773610760a6eb7d2b05102343d64bf72b089e`. No branch or source was deleted. The issue update was posted on October 10, 2026 ([comment](https://github.com/gyroflow/gyroflow/issues/250#issuecomment-6102702700)) after the Mac 1.0 release `plus-v1.0.0` (commit `755c9d3c`, DMG SHA-256 `8d48885f7cf26331b7cb2838970697d22f391a8ba683b0f5c1f98a62547d8600`) went live. The posted text adds the download link, the Mac/Apple silicon limit and the issues link to the draft below.

## Issue update draft — post after release checks

Following up on my earlier LUT work: the project has grown into **Gyroflow+**, an open-source community fork of Gyroflow focused on stabilizing and finishing log footage in one app.

Alongside Gyroflow's stabilization and trimming workflow, it adds LUT selection, recent LUTs, and exposure, temperature, tint, brightness, contrast, highlights, shadows, and saturation controls. Colors appear in the preview and are applied to the stabilized export. Originals remain untouched, and saved projects retain editable settings.

The newer color pipeline uses **OpenColorIO** for the color operations, including its CPU processor for export and generated GPU processing for preview. We retain integration code to connect it to Gyroflow's video pipeline and controls. This has also let us improve performance compared with the early implementation.

I chose to develop a fork because the work expanded beyond the original LUT and brightness/contrast patch into a broader color workflow, with its own testing and packaging needs. Keeping it separate gives us room to iterate and ship builds independently. It builds on Gyroflow's work and isn't an official Gyroflow release; focused upstream contributions are still welcome.

**App information and downloads:** https://gyroflowplus.com/  
**Source:** https://github.com/rsmith4321/gyroflow-plus

I've mainly tested with DJI O4 Pro D-Log M footage. The fork retains Gyroflow's camera support, but that doesn't establish color/LUT compatibility with every camera or profile. Use a LUT intended for your footage. This is non-destructive video grading, not RAW recovery.

The earlier [PR #1249](https://github.com/gyroflow/gyroflow/pull/1249) was closed because its limited implementation was superseded by this larger effort. Its code and discussion remain available. Includes AI-assisted code, reviewed and tested.

Feedback and reproducible reports would be welcome, especially for other cameras and LUTs.

## PR closure comment

I'm closing this PR because the initial LUT and brightness/contrast implementation has been superseded by a larger color workflow in my [Gyroflow+ fork](https://github.com/rsmith4321/gyroflow-plus).

The newer work uses OpenColorIO for the color operations in preview and export, and adds exposure, temperature, tint, highlights, shadows, and saturation alongside the existing controls. Its scope and testing/packaging needs have grown beyond this initial patch, so I'll maintain and iterate on it in the fork. This doesn't imply that LUT support is resolved in upstream Gyroflow; focused future upstream contributions remain possible.

Thank you for Gyroflow and the original discussion. I'm preserving this PR's code and discussion for reference, and will follow up in #250 with the app link once a usable packaged build is ready.

## Publication checks

- Do not post the issue announcement until the linked page offers an actual usable packaged build with its platform and verification limits clearly stated.
- Recheck the features, links, download availability, and PR status against current source and release evidence immediately before posting.
- Use the official OpenColorIO implementation wording only for the build actually offered; do not imply the legacy Cargo default uses it.
- Do not call upstream abandoned, claim universal camera/LUT compatibility, or claim RAW highlight recovery.
- Record the posted comment URL and exact release/artifact identity in project continuity.
