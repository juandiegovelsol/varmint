# Charts placed together lose parts of themselves

### What happens
`recording.mp4` some charts change what they show. Several things about these charts go wrong in
this clip: in the final dimensions of the charts, in the area the points are drawn in, and in the
position of the labels and controls.

Fix every problem you find in the clip that does not match the expected behavior below.

### Expected
- At every moment of the clip, all labels and controls of a chart are shown whole, within the
  chart's dimensions and without overlaps.
- The area the points are drawn in keeps the size it was given.
- Charts side by side share one height, stacked charts share one width, the areas their points
  are drawn in line up, and every chart stays within the row or column it is placed in.
- Everything else should keep looking and behaving as it does now.

## Attached visual evidence

- `/app/.harbor_assets/recording.mp4`

Inspect the attached video before making changes. You can pull individual frames out of it with
`ffmpeg`.
