# tickMinStep Ignored for Some Scales

### Bug Description

The screenshot below shows the rendered output for an affected case, where the axis was configured with `tickMinStep: 3`, a minimum the rendered tick interval must respect regardless of whether the scale's domain ascends or descends. The affected scale kind and the axis definition are visible in the image.

![Bug screenshot, rendered axis for the affected case](/app/.harbor_assets/bug.png)

Scale kinds with their own specialized tick behavior, such as logarithmic or time-based scales, are outside the scope of this report.