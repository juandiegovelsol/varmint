# [BUG] A quality/gear effect's bonus for Tests silently stops applying

**Describe the bug**
An Active Effect that's supposed to add a bonus to a character for certain Tests no longer does
anything. There's no error or warning anywhere — the effect is just quietly inert, and the roll
dialog never reflects it.

This particular effect is an older one: it was set up on this item a while ago, before a recent
system update, and hasn't been touched since. Whatever fixes it needs to apply automatically
wherever this shows up — however the old data happens to be stored, not just for this one example
— without disturbing anything else already configured on the same effect or interfering with how
the system brings other older content up to date.

**Screenshots**

<img width="1311" height="603" alt="Image" src="/app/.harbor_assets/bug_screenshot_1.png" />

The screenshot shows how this kind of effect is set up and what a correctly working one looks
like — the pictured effect's own stored values aren't necessarily the exact data that needs
fixing.

**Versions (please complete the following information):**
- FoundryVTT Version 13.351
- System Version 0.33.0
