# Cylinder bounds are mislabeled in Voxel Inspector

### What happened?

For cylinders, the Voxel Inspector's Bounds and Clipping panels should let you independently
adjust the shape's height range and its angular range. The screenshots below show the current
behavior.

![Image](/app/.harbor_assets/bug_screenshot_1.png)

![Image](/app/.harbor_assets/bug_screenshot_2.png)

### Other things noticed while investigating

- Some checkboxes in the Display panel end up in the opposite state from the one selected.
- The Inspector sometimes shows the wrong shape's Bounds/Clipping editor for the loaded primitive.
- Some sliders in the Transform panel rotate the primitive around the wrong axis.
- After switching to a different voxel primitive, the Shader panel can still show status left
  over from the previous one.
