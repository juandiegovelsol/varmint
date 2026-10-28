## Description

The **Review settings -> Review scores** page is behaving unpredictably for organisers trying to set up or tidy up their scoring categories. A handful of screenshots from a session poking at this page are attached.

At a high level: once you start adding score rows or a whole new category with the **+** controls, the page gives you no clean way to walk any of that back if you change your mind mid-edit, and it isn't consistent about telling you when something you typed — whether in a row you just added or one that was already there, in either of the score categories — won't actually be kept. Rows that end up half-finished, categories that never got a name, and score values that plainly aren't numbers all seem to slip through without the page saying anything useful about it — sometimes nothing is saved and nothing is said, sometimes something ends up saved that clearly shouldn't have been, and on the one occasion a validation error does surface, it shows up as a generic banner rather than pointing at what actually needs fixing.

None of this is exotic — it's the general "the form doesn't push back when it should, and doesn't offer a way out once you've committed to an edit" family of problem — but there is more than one distinct way it shows up on this page.

## Attached visual evidence

- `/app/.harbor_assets/bug_screenshot_1.png` — bug_screenshot (screenshot 1)
- `/app/.harbor_assets/bug_screenshot_2.png` — bug_screenshot (screenshot 2)
- `/app/.harbor_assets/bug_screenshot_3.png` — bug_screenshot (screenshot 3)
- `/app/.harbor_assets/bug_screenshot_4.png` — bug_screenshot (screenshot 4)
- `/app/.harbor_assets/bug_screenshot_5.png` — bug_screenshot (screenshot 5)

These files are available inside the container and are part of the bug report; read them before making changes.
