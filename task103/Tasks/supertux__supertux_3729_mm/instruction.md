# Some coins misbehave in the cave

### What happens
`recording.mp4` is an uncut run through a cave basin. Twice during the clip, Tux does something that releases a group of new coins. From the first of those moments until the end of the clip, the released coins do not behave the way coins in this game should. The coins that were already placed in the level, Tux, the animals and the scenery in the recording are correct.

### Expected
Each group of released coins should behave like a normal coin burst in this game, from the moment they spread out of their block until they come to rest and Tux goes back to collect them. Once a coin is within the basin's surrounding environment, it should drift down slowly, from the moment it enters it. Fix every way the released coins behave wrongly in the recording.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4` (47 seconds)

You can inspect individual moments of the video by extracting frames from it with `ffmpeg`.

Inspect the attached file before making changes.