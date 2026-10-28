# Focus ends up in the wrong place

Two scenarios, A and B, are captured frame by frame in the attached images. Each caption states the action performed, and focus is shown exactly the way the page itself draws it. The mouse pointer stays where it last clicked.

Frames A0–A4 and B1–B3 come from the current page. In each scenario the last of them (A4 and B3) shows a wrong result. The Expected images show what that step should produce instead, and the Expected images after it (A5–A7 and B4–B8) show what the next key presses should do from there.

![A0](/app/.harbor_assets/A0.png)
![A1](/app/.harbor_assets/A1.png)
![A2](/app/.harbor_assets/A2.png)
![A3](/app/.harbor_assets/A3.png)
![A4](/app/.harbor_assets/A4.png)
![A4 expected](/app/.harbor_assets/A4_expected.png)
![A5 expected](/app/.harbor_assets/A5_expected.png)
![A6 expected](/app/.harbor_assets/A6_expected.png)
![A7 expected](/app/.harbor_assets/A7_expected.png)
![B1](/app/.harbor_assets/B1.png)
![B2](/app/.harbor_assets/B2.png)
![B3](/app/.harbor_assets/B3.png)
![B3 expected](/app/.harbor_assets/B3_expected.png)
![B4 expected](/app/.harbor_assets/B4_expected.png)
![B5 expected](/app/.harbor_assets/B5_expected.png)
![B6 expected](/app/.harbor_assets/B6_expected.png)
![B7 expected](/app/.harbor_assets/B7_expected.png)
![B8 expected](/app/.harbor_assets/B8_expected.png)

## Expected

Make both scenarios match the Expected images. They follow one acceptable outcome: at A4 and B3, focus may instead land on another button that can be used, and the later steps then apply the same way from that button. Which button receives focus may differ from the images; how the focused button is drawn may not.

Keep all other behavior unchanged, including what the earlier frames show.

## Attached visual evidence

- `/app/.harbor_assets/A0.png` … `A4.png`
- `/app/.harbor_assets/A4_expected.png` … `A7_expected.png`
- `/app/.harbor_assets/B1.png` … `B3.png`
- `/app/.harbor_assets/B3_expected.png` … `B8_expected.png`

Inspect every attached file before making changes. The images describe observable behavior; they do not prescribe source files, internal names, or an implementation strategy.
