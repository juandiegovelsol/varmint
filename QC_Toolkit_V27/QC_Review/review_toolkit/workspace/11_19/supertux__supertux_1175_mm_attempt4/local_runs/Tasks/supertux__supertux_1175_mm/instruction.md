# Harm in the ice cave does not follow the game's own rules

### What happens
`recording.mp4` (42 seconds) shows Tux and some of the level's creatures in five short scenes of the
same ice cave. Several things go wrong in this clip:
- in how close something has to come before it is harmed;
- in how a meeting between Tux and a creature ends;
- in what a hit costs Tux, and in what keeps him safe;
- in where some harm lands;
- in when some things react to Tux.

Fix every problem you find in the clip that does not match the expected behavior below.

### Expected
- Only real contact harms Tux or a creature; a slight touch at an edge does not, although in the
  clip it does. Harm lands where it comes from.
- Things react to Tux when he comes near them, as one of them does in the clip.
- A meeting between Tux and a creature ends the usual way for both of them.
- Every hit costs Tux the same single step, and while he is protected nothing can harm him.
- Everything else should keep looking and behaving as it does now.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4`

Inspect the attached video before making changes. You can pull individual frames out of it with
`ffmpeg`.
