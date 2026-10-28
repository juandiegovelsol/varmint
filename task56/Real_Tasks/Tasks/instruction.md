# Unexpected interaction behavior

The recording below shows a keyboard interaction with a component of this repository, in the selection mode the recording puts it in, and the outcome that interaction produces. That outcome is wrong.

Reproduce the interaction, then make the component behave like this in that mode:

- Moving through the items with the keyboard only moves the focus: the current selection stays where it is and no selection event is emitted. This holds for every step, including the moves that jump straight to either end of the list.
- Moving through the items always lands on an item that can be selected, and running off either end of the list continues onto the opposite end.
- Moving on from an item that was just selected with the pointer continues from that item.
- Explicitly activating the focused item with the keyboard selects it and emits the selection event, carrying the payload the recording shows for that event.
- The selected state exposed to assistive technology follows the selection, never the focus.

Behavior that is already correct, both in this component and in anything it shares code with, must keep working.

![Issue](/app/.harbor_assets/bug.gif)
