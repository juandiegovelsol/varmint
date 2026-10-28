# Canvas rendering and exported SVG disagree for a character with its own offset

The exported SVG rendering of a text object does not match its canvas rendering. Two still frames of the same text object are provided:

- `/app/.harbor_assets/canvas_render.png` — the canvas rendering.
- `/app/.harbor_assets/exported_render.png` — the exported SVG rendering of that same text object.

Agreement must hold for a character with its own offset, when more than one such character appears on the same line, and for one on any line of a text with several lines.

The disagreement is not confined to where a character sits. Agreement must also hold for the thickness of text decorations, both where the text object declares one and where an individual character declares its own, and that thickness must not vary with the scale applied to the text object. It must hold as well when the text follows a path, where each character is rotated to the curve.
