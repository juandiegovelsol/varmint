# Objects on a terrace are not drawn where or how they were placed

### What happens
In `recording.mp4`, several of the objects placed on the terrace visible in the video are not
drawn where or how they were placed. These are separate, independent defects, each affecting a
different kind of object; fixing one does not fix the others.

### Expected
Every object renders in the position and orientation it was placed in. This must hold for any
such node anywhere in the world and however it was placed or turned, not only at the spots shown
in the video.

### Environment
All.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4`

You can inspect any moment of the video by pulling frames out of it with `ffmpeg` (installed in
the image). Inspect the attached file before making changes. The video describes observable
behavior; it does not prescribe source files, internal names, or an implementation strategy.
