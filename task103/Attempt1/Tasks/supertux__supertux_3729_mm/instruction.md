# Coins from a bumped bonus block misbehave in the flooded cave

### What happens
`recording.mp4` is an uncut run through a flooded cave basin. About 7 seconds in, Tux bumps a bonus block from below and it bursts into coins. From that moment until the end of the clip, the coins released by that block do not behave the way coins in this game should: more than one thing goes wrong between the moment they leave the block and the moment they should come to rest. The coins that were already placed in the level, Tux, the fish and the scenery all behave normally.

### Expected
Coins released by a bonus-block burst should behave correctly for their whole life in the clip: from leaving the block, through falling into and moving through the water, to coming to rest. In particular, once a coin is in the water it should slow to a gentle, drifting sink, however hard it hit the surface, instead of reaching the bottom almost at once. Fix every problem the recording shows, not only the first one you notice.

### Environment
All

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4` (44 seconds)

You can inspect individual moments of the video by extracting frames from it with `ffmpeg`.

Inspect the attached file before making changes. It describes observable behavior; it does not prescribe source files, internal names, or an implementation strategy.
