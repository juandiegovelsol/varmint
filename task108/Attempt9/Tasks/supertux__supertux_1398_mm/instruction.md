# Some objects misbehave in the forest

### What happens
`recording.mp4` is an uncut clip in a forest level. Several things that happen with the objects Tux grabs in the video are not how those objects work in this game. While Tux carries one, it is on the wrong side of him; when he throws one, it goes the wrong way and ends up sinking into the ground; Tux can pass through one that is lying on the ground; and a creature one lands on turns into ice. Other problems involving these objects are only visible in the recording, in how one falls (it slows down at one point) and in how it and the other things in the level affect each other.

### Expected
The objects that are grabbed in the video should behave like they normally do in this game, in every situation the clip shows: while Tux carries them (held in front of him), when he lets go of them (thrown the way he is walking, coming to rest on top of the ground), while they fall, when they meet other things in the level, and once they are lying on the ground (solid for Tux, who stops at them or stands on them). The game treats everything by the same rules, so the other problems show up in the recording as things that don't match the same kind of thing elsewhere in the same clip, or that look out of place in this level. Fix every problem involving these objects that you can see in the recording.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4` (26 seconds)

Inspect the attached video before making changes. You can pull individual frames out of it with
`ffmpeg`.
