# Ship is damaged when performing the action shown in the recording

### What happens
`recording.mp4` shows a ship performing an action at a station. The action does not
go the way it is set up to go, and the ship does not come out of it unharmed.

### Expected
Performing the action shown in the recording must not damage the ship at all, at the spot shown in
the video or at any other equivalent spot of the same station. The hull-integrity readout stays at
100% for the whole action, and the ship's motion follows the speed shown on the HUD in the video
straight away, with no delay at the start.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4`

You can inspect the video frame by frame with `ffmpeg` (installed in the image), e.g. extracting
still frames at specific timestamps to look closely at the HUD and the ship.

Inspect the attached file before making changes. The video describes observable behavior; it does
not prescribe source files, internal names, or an implementation strategy.