# Focus ends up in the wrong place

Two scenarios, A and B, are captured frame by frame in the attached images. Each caption states the action performed, and focus is shown exactly the way the page itself draws it.

Frames A1–A4 and B1–B3 come from the current page. In each scenario the last of them (A4 and B3) shows a wrong result. The Expected images show what that step should produce instead, and the Expected images after it (A5–A7 and B4–B7) show what the next key presses should do from there.

![Scenario A](/app/.harbor_assets/screen.png)
![A1](/app/.harbor_assets/focus_trace_1.png)
![A2](/app/.harbor_assets/focus_trace_2.png)
![A3](/app/.harbor_assets/focus_trace_3.png)
![A4](/app/.harbor_assets/focus_trace_4.png)
![Expected A4](/app/.harbor_assets/expected_A.png)
![Expected A5](/app/.harbor_assets/expected_A5.png)
![Expected A6](/app/.harbor_assets/expected_A6.png)
![Expected A7](/app/.harbor_assets/expected_A7.png)
![B1](/app/.harbor_assets/disabled_trace_1.png)
![B2](/app/.harbor_assets/disabled_trace_2.png)
![B3](/app/.harbor_assets/disabled_trace_3.png)
![Expected B3](/app/.harbor_assets/expected_B.png)
![Expected B4](/app/.harbor_assets/expected_B4.png)
![Expected B5](/app/.harbor_assets/expected_B5.png)
![Expected B6](/app/.harbor_assets/expected_B6.png)
![Expected B7](/app/.harbor_assets/expected_B7.png)

## Expected

Make both scenarios match the Expected images, including how focus is drawn. The Expected images follow one acceptable outcome; what matters is where focus goes relative to the buttons on the page. If focus lands on a different button at A4 or B3, the later steps apply the same way from that button.

Keep all other behavior unchanged, including what the earlier frames show.

## Attached visual evidence

- `/app/.harbor_assets/screen.png`
- `/app/.harbor_assets/focus_trace_1.png` … `focus_trace_4.png`
- `/app/.harbor_assets/expected_A.png`, `expected_A5.png` … `expected_A7.png`
- `/app/.harbor_assets/disabled_trace_1.png` … `disabled_trace_3.png`
- `/app/.harbor_assets/expected_B.png`, `expected_B4.png` … `expected_B7.png`

Inspect every attached file before making changes. The images describe observable behavior; they do not prescribe source files, internal names, or an implementation strategy.
