# Regression when built-in actions are removed

### What happened?
Normally, when a built-in action is removed from the editor's action set, its corresponding entry disappears from the menus. Removing only part of a related group of actions still behaves correctly.

Removing an entire group causes the regression. The screenshot below shows one menu in that state, and it is not the only menu affected, and not the only section of the menu that has the regressive behavior.

![bug_screenshot](/app/.harbor_assets/bug.png)

---
*Visual evidence is available in `/app/.harbor_assets/`. Open the screenshot(s) to understand the visual defect before writing your fix.*
