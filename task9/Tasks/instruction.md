# Wrong day marker shape

## Visual evidence
![before](/app/.harbor_assets/before.jpg)

## Symptom

Day markers in this calendar dialog are always plain circles, even though the
calendar's theme is meant to control that outline shape. Wherever a day cell's
shape is drawn, it ignores the theme and falls back to a circle.

## Task

Fix the calendar so day cells consistently use the shape from the theme,
everywhere that shape is drawn.
