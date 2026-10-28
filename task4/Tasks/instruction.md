# Full-circle polar chart is inconsistent with its own axis

I have a polar chart whose angular axis spans the whole circle, one categorical series per spoke,
with a tooltip enabled.

Hovering it gives me this, and the result depends on which part of the circle I point at:

![image](/app/.harbor_assets/bug.png)

And this is what it draws for the data I passed in, with no pointer involved at all:

![image](/app/.harbor_assets/mismatch.png)

## What is the expected behavior?

The chart should be self-consistent everywhere on the circle: for any spoke, the series it is
labelled with, the series drawn on it, and the series a hover near it resolves to must all be the
same one — and a hover must resolve to the spoke nearest the pointer, reporting that series' own
point on the chart.

This has to hold for any number of series, and whatever start and end angle the circle is laid out
with.
