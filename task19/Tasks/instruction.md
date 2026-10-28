# Pie chart rendering produces unexpected results

<img width="1270" height="868" alt="Image" src="/app/.harbor_assets/bug.png" />

## Expected behavior

Both charts in the screenshot draw the same dataset. They differ by the one extra setting visible
on the second, and on this dataset that setting should have made no difference at all. Instead,
every boundary in the lower chart has rotated away from the upper one.

The amount that setting asks for should be committed:

- to nobody, when every sector in the chart already reaches it on its own;
- against the arc the sectors are actually given to divide, not the arc before the chart's other
  spacing has been taken out of it;
- never to a sector holding no value;
- and never in a total larger than the arc can supply.

Otherwise sectors split the arc in proportion to their values. All of this holds for a pie drawn
across part of a circle as well as a whole one.
