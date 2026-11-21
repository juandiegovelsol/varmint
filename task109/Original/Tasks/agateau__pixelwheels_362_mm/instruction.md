# Fired rocket renders in front of the start/finish banner instead of behind it

### What happens
In `recording.mp4` (9.5s), from about 0:00.9 to 0:01.2, the car's fired rocket crosses the
checkered banner stretched across the track on two angled poles. The rocket stays fully visible,
drawn over the stripes and poles instead of disappearing behind them.

### Expected
As the rocket crosses under the banner, it should be hidden behind the banner and its poles,
not drawn on top of them.

### Environment
Desktop build. All platforms.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4`

Inspect the attached video before making changes. You can pull individual frames out of it with
`ffmpeg` to look more closely at specific moments. The video describes observable behavior; it
does not prescribe source files, internal names, or an implementation strategy.
