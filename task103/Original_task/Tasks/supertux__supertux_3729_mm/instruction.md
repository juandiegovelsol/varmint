# Coins dropped into the water sink straight down and freeze at the bottom

### What happens
In `recording.mp4` (0:00-0:14), several coins knocked loose from a block fall into the water-filled chasm below it. Once in the water they drop straight to the chasm floor and sit completely still there for the rest of the clip, never slowing or drifting.

### Expected
Coins falling into water should keep gently sinking and drifting for a while after they enter it, the way other falling objects behave once submerged, instead of dropping to the bottom and stopping almost immediately.

### Environment
All

### Where to look
Pull frames with `ffmpeg` at 0:02 and 0:10 and compare them: the coins sit in the exact same place in both, with no visible change between them.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4` (14 seconds)

You can inspect individual moments of the video by extracting frames from it with `ffmpeg`.

Inspect the attached file before making changes. It describes observable behavior; it does not prescribe source files, internal names, or an implementation strategy.
