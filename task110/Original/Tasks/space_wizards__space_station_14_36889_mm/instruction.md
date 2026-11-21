# Firelock's warning light doesn't track the door

### What happens
In `recording.mp4`, a closed, hazard-striped firelock has a small warning light glowing beside it
(0:00-0:06). Around 0:07 the door's panel visibly darkens as it starts moving. The light ignores
this, glowing unchanged for the rest of the clip (0:07-0:14).

`recording.mp4` (14 seconds)

### Expected
The warning light should go dark as soon as the door leaves its closed state, not keep glowing
unchanged while the door itself is visibly moving.

### Environment
All.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4`

Inspect the attached video before making changes. You can pull individual frames out of it with
`ffmpeg` if you need a closer look at a specific moment. The video describes observable behavior;
it does not prescribe source files, internal names, or an implementation strategy.
