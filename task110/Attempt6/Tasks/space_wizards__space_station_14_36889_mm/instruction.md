# The elements in the video misbehave

### What happens
`recording.mp4` shows a row of the elements seen in the video, on a test bench, each set between
a small room and whatever is on its far side. Several things about these elements go wrong in this clip: in
their warning lights, in the way the element moves, and in what ends up on each side of a shut element.

Fix every problem you find in the clip that does not match the expected behavior below.

### Expected
- A shut element keeps what is on one side from reaching the other, and its warning says what kind of danger
  it is holding back.
- The warning only shows while the element is shut.
- A element shuts controlled.
- Every element of a element stays aligned with the rest of it.
- Everything else should keep looking and behaving as it does now.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4`

Inspect the attached video before making changes. You can pull individual frames out of it with
`ffmpeg`.