There is a bug in this codebase: when an SVG document like the one below is loaded and drawn, the canvas is incorrectly rendered. Change the implementation so loading documents of this form produces the intended render.

```svg
<svg xmlns="http://www.w3.org/2000/svg">
<style>
.blue { fill: blue; }
</style>
<style>
.red { fill: red; }
</style>
<circle class="blue" r="45" cx="50" cy="50"></circle>
<circle class="red" r="45" cx="150" cy="50"></circle>
</svg>
```

Actual:

![actual](/app/.harbor_assets/actual.png)

Intended:

![intended](/app/.harbor_assets/intended.png)

Matching shapes should receive the fills declared for their classes in the document styles, including when those rules live in more than one style element, when a shape carries more than one class, and when a fill value references a paint server such as `fill: url(https://example.com/paint.svg#swatch)`.
