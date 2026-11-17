# A line in the recording does not match what the recording shows

### What happens
`recording.mp4` shows a line drawn from the player character. At several moments of the clip
that line does not match what the clip itself shows: the screen at the very start of the clip, or what
happens in the clip right after that moment. These are separate, independent defects, each in a
different situation; fixing one does not fix the others.

### Expected
The line always matches the opening screen of the clip and what happens right after in the clip. This
must hold in every situation, not only in the ones shown in the clip.

### Environment
All.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4`

Watch the attached video before making changes. You can pull individual frames out of it with `ffmpeg`
(installed in the image).
