# Scenario selection window: icon areas are no longer accessible

### Describe the bug

In the scenario selection dialog, right-clicking on the icon columns no longer works correctly. The exact incorrect behavior is visible in the screenshots below.

The screenshots below were captured while reproducing the bug:

![Screenshot 1](/app/.harbor_assets/bug_1.png)
![Screenshot 2](/app/.harbor_assets/bug_2.png)
![Screenshot 3](/app/.harbor_assets/bug_3.png)
![Screenshot 4](/app/.harbor_assets/bug_4.png)

![Screenshot 5](/app/.harbor_assets/bug_5.png)
![Screenshot 6](/app/.harbor_assets/bug_6.png)

![Screenshot 7](/app/.harbor_assets/bug_7.png)
![Screenshot 8](/app/.harbor_assets/bug_8.png)

Fix the scenario selection dialog so that right-clicking on each icon area works correctly, matching the expected behavior shown in the screenshots. The file-location/map-type popup shown in the screenshots should not be removed -- it should still be reachable by right-clicking elsewhere on the row, matching what the screenshots show. The incorrect behavior shown in the screenshots may not be confined to the areas shown above -- check the rest of the dialog for any other right-click area that could be similarly affected, and make sure your fix leaves each of them working as it did before.

One more thing worth checking while you're in this dialog. In the panel below the list that describes the currently selected map, check whether the "Map difficulty" label still sits where the screenshots show it, relative to the panel.
