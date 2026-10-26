# Progress

| Phase | Status |
|---|---|
| 0 Board reset | done |
| 1 Core (radar, night score, alarm, sunrise, chime, wake message, demo mode) | software done and running on the board; radar on hardware (T0, T1) not yet tested |
| 2 E-paper card | firmware written, not yet compiled or flashed; app side (card push, keys) written, unit tests pass |
| 3 Important dates, tiny steps, predictor | written, unit tests pass; TabPFN not installed on the board, logistic fallback in use |
| 4 Rain | MCU microphone features and rule written, sketch compiles; microphone not wired, not tested on hardware |
| 5 README and photos | README updated; photos not yet taken |

## What works
- Alarm decision with hard-coded health limits (12/12 cases), wake message validator (20/20),
  night score tests, tiny-step and rain logic tests (5/5, `tests/test_steps_rain.py`).
- Sketch with backup alarm and microphone code compiles on the board (97,240 bytes flash, 43,789 bytes RAM).

## What does not work yet / not tested
- The app has not been restarted on the board with the new sketch.
- E-paper card: needs `secrets.h` and the panel selected in Seeed_GFX `driver.h`.
- Microphone register settings unverified until the INMP441 is wired (block count on the page is the self-check).
- TabPFN: not installed (needs torch on the board).
