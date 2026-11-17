# Hook aim preview line never appears, no matter which way the player aims

### What happens
In `recording.mp4` (0:19 long), from about 0:10 to the end, the player stands on a platform and
sweeps their hook aim through several directions, then fires it. No thin preview line ever appears
in the sky tracing the aim direction, even though the weapon pose clearly changes each time.

### Expected
A thin line should be visible stretching out from the player along whatever direction they are
currently aiming, updating as the aim direction changes, so the player can see roughly where the
hook will travel before they fire it.

### Environment
All.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4`

Inspect the attached video before making changes. You can pull individual frames out of it with
`ffmpeg` (installed in the image) if you need to look more closely at a moment. The video
describes observable behavior; it does not prescribe source files, internal names, or an
implementation strategy.
