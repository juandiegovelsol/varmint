# Some coins misbehave in the flooded cave

### What happens
`recording.mp4` is an uncut run through a flooded cave basin. Partway through the clip, Tux does something that releases a group of new coins. From that moment until the end of the clip, those coins do not behave the way coins in this game should. The coins that were already placed in the level, Tux, the fish and the scenery in the recording are correct.

### Expected
The released coins should behave correctly for as long as they are on screen. Once a coin is in the water it should drift down slowly, however hard it hit the surface, but not crawl: sinking from the height of the block Tux hits down to the basin floor directly below it should take about a second and a half. Fix every way the released coins behave wrongly in the recording.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4` (44 seconds)

You can inspect individual moments of the video by extracting frames from it with `ffmpeg`.

Inspect the attached file before making changes.