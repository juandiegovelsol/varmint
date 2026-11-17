# The hook collision line does not show what the hook will do

### What happens
`recording.mp4` (1:02) shows the client's *Hook Collisions* settings page, which shows how the
player's own hook collision line is configured, what each line colour means, and a preview of how the
line should look, together with a player using the grappling hook on a practice level. At several
moments the line contradicts the settings page or what the hook does right after it is fired: in its
colour, in where it ends, in how it is drawn, or by not being drawn at all. These are separate, independent defects, each affecting a different situation; fixing
one does not fix the others.

### Expected
While the setting is on, the line is always drawn from the player along the current aim, and it never
contradicts the settings page or what the hook does when it is fired along that aim. This must hold
everywhere, not only in the situations shown in the video.

### Environment
All.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4`

Inspect the attached video before making changes. You can pull individual frames out of it with
`ffmpeg` (installed in the image); some of the relevant moments last only a few frames. The video
describes observable behavior; it does not prescribe source files, internal names, or an
implementation strategy.
