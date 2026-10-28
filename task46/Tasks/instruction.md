### Description

The two screenshots below show the same wxWidgets sample window. Its paint handler is the
same in both runs and issues the same drawing calls; the runs differ only in how the handler
remaps drawing coordinates before it draws.

![first run](/app/.harbor_assets/bug.png)

![second run](/app/.harbor_assets/after.png)

The second screenshot is correct. Fix the library so that a paint handler always gets exactly
the area it asked to be restricted to, both reported back and actually honoured, in whatever
coordinate mapping is currently in effect -- including when that area was given in the
window's own pixel coordinates, when it has been cleared again, and when the mapping is
changed while the restriction is still in effect.
