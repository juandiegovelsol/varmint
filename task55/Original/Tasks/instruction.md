# Bug: in a collaborative session, carets and selections end up in the wrong place

The document text itself replicates fine between collaborators. Where everybody ends up
*pointing* does not.

## What happens

When several people work in the same document, each of them should be able to see where the
others are -- a small labelled caret at another person's cursor, a highlighted band over
whatever they have selected -- and each of them should keep their own place in the text while
the others work. None of that holds up in ordinary use. What you see of somebody else is
usually where they were a while ago rather than where they are now: it only catches up when
somebody happens to type into the document, so watching a colleague click around or drag out a
selection changes nothing on your screen until a character is typed somewhere, and even
somebody who has left the session can still be sitting there. Your own place is no safer -- an
edit made earlier in the document leaves your caret and selection behind, pointing at text you
never put them on, so what you type next lands in the wrong spot. It is worst wherever a
position is not simply so many characters into a line: on a blank line, at the very start or
end of a paragraph, or across a selection that runs from one paragraph into another, where a
person's caret or one end of their selection turns up in a paragraph they are not in, or does
not appear at all.

## Expected behaviour

Everyone's caret and selection should reach the other participants on their own and be
reflected straight away -- nobody should have to type anything to make another person's
current position show up, and what is shown must be where that person is now. Nobody's own
caret or selection should be dragged off the text it was left on by somebody else's edit. And
a position should land where it actually is, including on blank lines, at paragraph edges, and
at both ends of a selection that spans more than one paragraph.

## Impact

100% reproducible in a two-pane collaborative session.

## Attached visual evidence

Three frames captured from a screen recording of the bug, in a two-pane collaborative
session -- the same document open twice, side by side, each pane with its own debug panel
underneath showing that pane's own live selection offsets. In each frame both panes agree on
the text, and the debug panels are what let you read off where each person actually is.

- `/app/.harbor_assets/bug_screenshot_1_3.png` — both copies of the document are empty
  (placeholder text showing) and both panels report their own caret at offset 0. The right
  pane draws the other person's labelled caret at the very start of the line; the left pane
  draws it roughly 40% of the way across the empty first line, which in a document with no
  text in it is a position no caret can occupy.
- `/app/.harbor_assets/bug_screenshot_1_2.png` — both panes show the same 17-character text.
  The panels report the two people at offset 0 (left pane) and offset 17, the end of the
  text (right pane). The left pane draws the other person's caret at the end of the text,
  which matches. The right pane draws it about ten characters into the text, although the
  person it belongs to is at offset 0.
- `/app/.harbor_assets/bug_screenshot_1_1.png` — the same session a little later, both panes
  showing the same 20-character text, with the panels reporting offset 20 (left pane, the
  end) and offset 3 (right pane). Here neither drawn caret matches: the left pane draws the
  other person's caret near the end of the text although that person is at offset 3, and the
  right pane draws it a few characters in although that person is at offset 20.
