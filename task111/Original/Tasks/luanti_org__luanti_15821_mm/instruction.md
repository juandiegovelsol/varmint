# Node selection outline draws as disconnected fragments instead of a full box

### What happens
In `bug.mp4`, from 0:00 to 0:04, while aimed at the grass-topped block, the yellow/black selection wireframe never forms one closed box: only a short line near the top and two unconnected pieces lower down show, with no left or right side lines, so the outline looks torn apart.

`bug.mp4` is about 16 seconds long.

### Expected
The selection outline should draw as a single, complete, closed rectangular box around whichever block is targeted, with all four sides connected, the same way it does in `expected.mp4` (also about 16 seconds long) for the same view of the same block.

### Environment
All (observed on desktop OpenGL rendering).

## Attached visual evidence

- `/app/.harbor_assets/bug.mp4`
- `/app/.harbor_assets/expected.mp4`

You can inspect either video by pulling individual frames out of it with `ffmpeg` (installed in this image). Inspect both videos before making changes. The videos describe observable behavior; they do not prescribe source files, internal names, or an implementation strategy.
