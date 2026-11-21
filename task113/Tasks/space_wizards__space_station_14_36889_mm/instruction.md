# The doors in the video misbehave

### What happens
`recording.mp4` shows a row of doors on a test bench, each set between a small room and whatever
is on its far side. Several things about these doors go wrong in this clip: in their warning lights,
in the way a door moves, and in what ends up on each side of a shut door.

Fix every problem you find in the clip that does not match the expected behavior below.

### Expected
- A shut door keeps what is on one side from reaching the other, and its warning says what kind of
  danger it is holding back.
- The warning only shows while the door is shut.
- A door shuts smoothly.
- Every part of a door stays aligned with the rest of it.
- Everything else should keep looking and behaving as it does now.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4`

Inspect the attached video before making changes. You can pull individual frames out of it with
`ffmpeg`.
