# Bug: in a collaborative session, carets and selections end up in the wrong place

The attached frames are from a two-pane collaborative session. Each pane's own debug panel,
underneath its editor, reports that pane's own live selection offset.

Further things break, independent of what the frames show. Another participant moving
their caret, selecting text, or leaving the session should be reflected every time it
happens; none of it is. An edit made earlier in the document leaves your own caret and selection behind,
on text they no longer belong on. And any position that is not simply so many characters
into a line -- a blank line, a paragraph edge, a selection that spans two paragraphs --
lands wrong.

100% reproducible in a two-pane collaborative session.

## Attached visual evidence

- `/app/.harbor_assets/bug_screenshot_1_1.png`
- `/app/.harbor_assets/bug_screenshot_1_2.png`
- `/app/.harbor_assets/bug_screenshot_1_3.png`
