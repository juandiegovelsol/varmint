# Things on the terrace in the video are not drawn the way they were built

### What happens
`recording.mp4` (57 seconds) is a fly-around of a small terrace, recorded from this build. Several of
the things on it are not drawn the way they were built: in where some objects sit relative to what
they belong to, in how some pieces join their neighbours, in the faces some blocks show, in the
water, and in how some plants are laid out. These are separate problems; fixing one does not fix
another.

Fix every problem you find in the clip that does not match the expected behavior below.

### Expected
- Every object is drawn in its own place and turned the way it was placed, whichever way that is,
  and anything fixed to something stays on it.
- Pieces that join up with their neighbours join every neighbour they are allowed to join, and run
  towards it.
- A block shows each of its faces in the right place and the right way round, however it is turned.
- Nothing, solid or water, can be seen into or through where its surface should be closed.
- Running water looks like it runs the way it flows.
- Everything else should keep looking and behaving as it does now. The game draws everything by the
  same rules, so each problem shows up as something that does not match the same kind of thing
  elsewhere in the clip, or that looks out of place.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4`

Inspect the attached video before making changes. You can pull individual frames out of it with
`ffmpeg`.
