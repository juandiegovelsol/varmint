# Elements in a small yard do not display what they should

### What happens
`recording.mp4` (0:32) shows a small yard: two floating elements hang side by side, and a penguin
walks a loop in front of them, carrying a smaller floating element above its head. Seen from the
front, all three floating elements are set up to display the same thing. From about 0:15 the camera
walks around the left floating element and then looks at the yard from behind. At several moments
of the clip, the floating elements and the penguin do not display what they should: they show the
wrong picture, or show a picture the wrong way round. These are separate, independent defects, each
affecting a different case; fixing one does not fix the others. The terrain, the hills and the sky
are drawn correctly.

### Expected
Each of these elements displays exactly what it was set up to display, at every moment and from
every side it is seen from. This must hold for any such element anywhere in the world and however it
is placed, turned or carried, not only for the elements and camera positions shown in the video.

### Environment
All.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4`

You can inspect any moment of the video by pulling frames out of it with `ffmpeg` (installed in the
image). Inspect the attached file before making changes. The video describes observable behavior; it
does not prescribe source files, internal names, or an implementation strategy.
