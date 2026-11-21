# Parts of the scene in the video are drawn wrong

### What happens
Several things go wrong in `recording.mp4`: in how some of the parts are put together, in what stays
visible from close by and from far away, and in how the game marks what the player points at.

Fix every problem you find in the clip that does not match the expected behavior below.

### Expected
- Every part faces the way it was placed and is drawn whole, from every side the camera can see.
- A part that links up with its neighbours links to them correctly.
- Nothing disappears into what it rests on, whether the camera is close by or far away, and nothing is drawn even slightly nearer than the surface it belongs to (this matters for blocks that have a second picture painted over their main one; blocks without one are fine as they are).
- What the player points at is marked by one closed box that fits around it, also for a part fixed to a wall.
- Everything else should keep looking as it does now.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4`

Inspect the attached video before making changes. You can pull individual frames out of it with
`ffmpeg`.
