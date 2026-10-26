# Progress

| Phase | Status |
|---|---|
| 0 Board reset | done |
| 1 Core (radar, night score, alarm, sunrise, chime, wake message, demo mode) | running on the board end to end: radar wired to the board, demo nap -> decision -> sunrise -> chime -> Gemma message -> card; radar accuracy about 80-90% (T0); movement calibration (T1) not yet tested |
| 2 E-paper card | flashed and working: 3.2 s refresh, alarm still rings when the card is off (T5); button test not yet run |
| 3 Important dates, tiny steps, predictor | running on the board: Gemma step splitting 4/5 model + 1 template (T6); TabPFN v2 used after 20 labelled mornings, rule before that (T7 on synthetic data) |
| 4 Rain | INMP441 wired and tested: rain detected, +15 min applied (T8) |
| 5 README and photos | README updated; photos taken |

## What works
- Alarm decision with hard-coded health limits (12/12 cases), wake message validator (20/20),
  night score tests, tiny-step and rain logic tests (6/6, `tests/test_steps_rain.py`).
- Sketch with backup alarm and microphone code compiles on the board (97,240 bytes flash, 43,789 bytes RAM).
- Radar wired to the board.
- Radar lines tested: 1790/1800 in a 30 min run, no bad lines (T2).
- Radar breathing / heart rate about 80-90% against a manual count and a reference heart rate (T0).
- Rain bonus tested: rain detected, +15 min applied (T8).
- Chime through the PAM8403 and a small cavity speaker on D3, tested by ear.
- TabPFN v2 installed and running on the board (T7).
- Card refresh 3.2 s; alarm unaffected when the card is unreachable (T5).
- Step splitting and step-size choice run on the board (T6, T7).
- Card text is turned into plain ASCII before sending (the card fonts have no curly quotes).

## What does not work yet / not tested
- Movement gains (T1): movement still jumps to 100 too easily.
- TabPFN accuracy on real mornings (T7): not yet measured, needs 20+ labelled mornings.
- Gemma steps sometimes restate the whole job or come out of order (T6); card buttons not yet tested.
