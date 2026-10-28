# Chart readout and keyboard focus

<img width="558" height="1071" alt="Image" src="/app/.harbor_assets/bug_screenshot_1.png" />

## Expected behavior

The screenshot shows three charts on one page, each captured at a different point reached during
keyboard navigation.

That is not correct. A reader who leaves one and comes back is never stranded: what they see
should always match where they are. Mind the difference between leaving and choosing: what the
reader puts away stays away until they move on, and then it returns at once.

Find and correct the state handling responsible. Look at the attached screenshot before making
any changes.
