# Some blocks in the video are drawn wrong

### What happens
Several things go wrong with the blocks in `recording.mp4`: in how some of them, like the track, are put together, in
what stays visible from close by and from far away, and in the box the game draws around the block the
player points at.

Fix every problem you find in the clip that does not match the expected behavior below.

### Expected
- Stairs, slabs and other shaped blocks face the way they were placed and are drawn whole, from every side the camera can see.
- A block that links up with its neighbours links to them correctly.
- Nothing disappears into what it rests on, whether the camera is close by or far away, and nothing is drawn even slightly nearer than the surface it belongs to (this matters for blocks that have a second picture painted over their main one; blocks without one are fine as they are).
- The block the player points at is marked by one closed box that fits around it, also for a ladder or a sign fixed to a wall.
- Everything else should keep looking as it does now.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4`

Inspect the attached video before making changes. You can pull individual frames out of it with
`ffmpeg`.
