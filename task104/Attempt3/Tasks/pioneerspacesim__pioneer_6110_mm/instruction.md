# Ship is damaged when performing the action shown in the recording

### What happens
`recording.mp4` shows a ship performing an action at a station. The action does not
go the way it is set up to go, and the ship does not come out of it unharmed.
The collision outlines of the ship and the pad already overlap while the ship sits still, although the video shows it resting clear of the pad. A ship that really lands on a pad must still be caught by it, and the ship must keep its overall proportions.

### Expected
Performing the action shown in the recording must not damage the ship at all, at the spot shown in
the video or at any other equivalent spot of the same station. The hull-integrity readout stays at
100% for the whole action.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4`

You can inspect the video frame by frame with `ffmpeg` (installed in the image), e.g. extracting
still frames at specific timestamps to look closely at the HUD and the ship.

Inspect the attached file before making changes. The video describes observable behavior; it does
not prescribe source files, internal names, or an implementation strategy.