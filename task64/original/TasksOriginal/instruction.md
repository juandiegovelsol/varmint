# Follow border gets chopped up by the UI panels

When you follow someone in a shared session, the editor draws a colored border around the edge of the viewport. The panels on screen (the menus, the toolbar, the side panels) break it up: wherever one meets an edge, the border is cut off there instead of carrying on across it, so instead of one clean frame you get a colored line that stops at every panel and only shows through in the gaps. The attached screenshot (`follow_border_cut_by_panels.png`, in this task's assets) shows it along the top edge, where the border stops dead at the menu bar.

It should be one unbroken frame sitting on top of the whole interface, and it should stay that way in every layout, including the stripped-down one where the usual panels are hidden. The border belongs to the follow experience, not to the panel chrome, so it should never break apart or drop out depending on what is on screen.
