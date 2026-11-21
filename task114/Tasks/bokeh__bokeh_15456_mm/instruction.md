# Plots placed together lose parts of themselves

### What happens
`layouts.png` shows several groups of scatter plots rendered in a browser: two plots side by side,
a row of four, a column of three, a small grid, and one plot on its own. Several things about these
plots go wrong in this screenshot: in how much room each plot gets, in the size of its plotting
area, and in where its axes, legend and toolbar end up. Most of these parts are drawn correctly
somewhere else in the same screenshot.

Fix every problem you find in the screenshot that does not match the expected behavior below.

### Expected
- Every plot shows its axes, title, legend and toolbar fully inside its own box, and none of them
  covers another one or the plotting area.
- A plotting area given a fixed size keeps exactly that size, wherever the plot is placed.
- Plots side by side in a row are equally tall, plots stacked in a column are equally wide, and
  plotting areas that share a row or a column of a layout line up with each other.
- Everything else should keep looking and behaving as it does now.

## Attached visual evidence

- `/app/.harbor_assets/layouts.png`

Inspect the attached screenshot before making changes. It describes observable behavior; it does
not prescribe source files, internal names, or an implementation strategy.
