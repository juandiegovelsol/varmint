# Submenu trigger stays visible with nothing usable inside it

### What happened?
Normally, when a built-in action is removed from the editor's action set, its corresponding entry disappears from the menus.


However, if every action belonging to one of the menu's submenus is removed this way (not just some of them, but all of them), the submenu trigger is left behind: it stays visible and clickable, but opens onto nothing usable.

![bug_screenshot](/app/.harbor_assets/bug.png)

### How can we reproduce the bug?
Remove every action that belongs to one of these submenus, then open the containing menu and click into that submenu.

---
*Visual evidence is available in `/app/.harbor_assets/`. Open the screenshot(s) to understand the visual defect before writing your fix.*
