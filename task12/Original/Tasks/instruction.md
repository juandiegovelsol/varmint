# tickMinStep Ignored for Some Continuous Scales

### Bug Description

When an axis specifies a minimum tick step, the rendered tick interval can still come out smaller than that minimum for some continuous scales.

For example: a left-oriented axis for a linear scale whose domain spans 0 to 12, with a minimum tick step of 3.

![Bug screenshot — rendered axis for the scale/axis definition above](/app/.harbor_assets/bug.png)

The screenshot shows the rendered axis for this specification. The tick interval it produces is smaller than the specified `tickMinStep`.

The tick interval should never be smaller than the specified `tickMinStep`, whether the scale's domain ascends or descends. For this example, every rendered tick step should be at least 3 (e.g., 0, 3, 6, 9, 12, rather than a smaller spacing).

This report is about ordinary continuous numeric scales (such as linear). Scale kinds with their own specialized tick behavior — such as logarithmic or time-based scales — are outside its scope.
