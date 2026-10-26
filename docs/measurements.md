# Measurements

Every number in the README comes from this file. Each entry: date, setup, trials, result.
Anything not tested yet says "not yet measured".

| ID | What | Result |
|---|---|---|
| B0 | Board baseline, LLM time to first token and tokens/s | 2.38 s first token (cold prompt); 4.42-4.45 tok/s generation; 6.5-7.4 tok/s prompt |
| T0 | Breath / heart rate vs manual count | about 80-90% against a manual breath count and a reference heart rate |
| T1 | Movement detection | not yet measured |
| T2 | Bridge rows, drops, max message size | 30 min real radar: 1790/1800 lines, 179/180 rows, 0 bad, no gap > 15 s; row message 33 bytes |
| T3 | Alarm decision and health limits (unit tests) | 12/12 cases pass |
| T4 | Wake message validation and generation time | 10 records: 8 valid first try, 2 after retry, 0 template; 20.3-37.9 s per message |
| T4b | Demo nap end to end | not yet measured |
| T5 | E-paper card refresh, latency, offline behaviour, buttons | full refresh 3186-3188 ms, POST to done 3189-3191 ms (5 pushes); card offline: alarm still rings; buttons not yet measured |
| T6 | Step splitting | 5 example jobs: 4 model steps passed the checker, 1 template; 17.8-19.1 s each; doable rating not yet measured |
| T7 | Step size choice, predictor fit/predict time | cold-start rule 6/6; synthetic held-out accuracy TabPFN 0.82, logistic 0.80; TabPFN fit 15.3 s, predict 17.4 s; real mornings not yet measured |
| T8 | Rain classifier | passed: rain detected, +15 min applied |

## Log

### 2026-10-26 B0 local model speed
- Setup: UNO Q 4 GB, llama.cpp llama-server 0.6.0-dev (build 11449), gemma-3-1b-it-qat-Q4_0.gguf,
  3 threads, context 1024, started by the systemd user service. Script `tests/llm_bench.py`
  (prompt "Say good morning in one short sentence.", max 32 tokens, temperature 0).
- Trials: 3.
- Result: time to first token 2.38 s (trial 1, 17 prompt tokens), 0.78 s (trials 2-3, prompt cache hit,
  5 new prompt tokens). Prompt 7.41 / 6.52 / 6.51 tok/s. Generation 4.44 / 4.42 / 4.45 tok/s.

### 2026-10-26 T2 Bridge path (partial)
- Setup: app running on the board, no radar connected. 12 valid CSV lines and 1 malformed line
  (`R,bad`) sent through `/api/inject` -> `inject_line` on the STM32.
- Trials: 1.
- Result: the next 10 s row arrived on Linux with lines=12, bad=1, presence=100, heart=62.0, distance=80.
  Long-run drop rate and real radar traffic: see the 30 min run below.

### 2026-10-26 T2 30 min run, real radar
- Setup: radar kit forwarder sending 1 s lines, app running normally, no demo nap or model calls
  during the window. Card pushes (5) and a person sitting/lying near the radar during the run.
- Trials: one 1800 s window (board time 1793021382-1793023182), counted from the SQLite rows.
- Result: 179/180 rows (the missing one is the window edge), 1790/1800 lines, 0 bad lines, no gap over 15 s.
  16 rows had fewer than 10 lines (min 4, max 14 in a row): lines arriving late land in the next row.
  Largest row message on the Bridge (msgpack, all fields at their widest values): 33 bytes, limit 256.

### 2026-10-26 T3 alarm decision and health limits
- Setup: `python tests/test_decision.py` on the PC (pure function, no hardware).
- Trials: 12 cases: good night; restless; restless + rain; rain only; slack 10 min; shifted yesterday at
  score 55 and at 35; low-confidence night; low-confidence rain; hard limit equal to normal; hard limit
  before normal; very poor + rain with 60 min slack.
- Result: 12/12 pass. Every case also checks extra <= 30 and final <= hard limit.
  Validator tests: 20/20 pass (`tests/test_validator.py`, includes the "2:10-3:30" range).

### 2026-10-26 T4 wake messages
- Setup: `tests/t4_messages.py` inside the app container on the board, 10 decision records
  (good, restless, restless + rain, slack 10, shifted yesterday at 55 and 35, not confident, rain only,
  score 45 with no slack, very poor + rain). Gemma 3 1B via llama-server, temperature 0.
- Trials: 10 messages.
- Result: 8 passed the validator on the first try, 2 after the retry, 0 needed the template.
  Time per message 20.3-37.9 s (retries are the slow ones). Every number and time passed.
  One known wording miss the validator cannot catch: a retry turned "you slept badly, but you
  already slept in yesterday" into "you've already had a restful sleep".
- Earlier runs of the same test while tuning the prompt (same day): 8/2/0 with "out of 100" rejected
  (fixed: the scale is now in the record); 4/1/5 when the model had to write the time itself
  (fixed: code adds the time); 10/0/0 but two +0 records claimed "extra time" (fixed: new validator rule).

### 2026-10-26 Build size with backup alarm and microphone code
- Setup: `arduino-cli compile --profile default -b arduino:zephyr:unoq` on the board, core 0.90.0.
- Result: 97,240 bytes of 786,432 flash (12%), 43,789 bytes of 262,144 RAM (16%).

### 2026-10-26 Radar first light (before T0)
- Setup: MR60BHA2 kit on the PC over the XIAO's USB-C (COM31), our forwarder sketch flashed to the XIAO,
  radar module firmware not changed. Person near the PC at 0.4-0.75 m; posture not controlled (not lying down).
- Trials: one 68 s capture, 68 lines, 1 per second.
- Result: presence 1 on all 68 lines. Breathing 1-23 per min (16-23 for the first 30 s, then falling to 1-9).
  Heart rate 79-102 bpm on 59 lines, 0 on 9 lines (no value from the radar). Distance 74 cm, then 40 cm.
  Movement 0 on 57 lines; 5-100 on 11 lines, mostly at distance jumps or isolated spikes.
- Not a T0/T1 result: no manual breath count or reference heart rate, and the person was not lying still.
  Movement gains (PHASE_GAIN, DIST_GAIN) still to be calibrated in T1.
- Earlier the same day the kit ran a people-tracking example: "Human Detected" with one target at
  0.5-1.0 m and speeds of 0, +/-17 and 35 cm/s, so the module firmware already has presence detection.

### 2026-10-26 TabPFN on the board
- Setup: `torch==2.14.1+cpu` and `tabpfn==2.2.1` in the app's venv, CPU only, Gemma stopped during the install.
  A first try with the default torch wheels pulled NVIDIA CUDA packages, filled /tmp with 1.3 GB and froze
  the board (power cycle needed); the CPU-only index fixed it. tabpfn 9.2.0 was tried first: its weights need
  an account and API key, so 2.2.1 (public v2 weights, 29 MB) is used.
- Trial: one run on 40 random rows x 4 features, then 5 predictions.
- Result: import 27.8 s, first fit 17.5 s (includes the weights download), predict 10.2 s. 5/5 predictions on
  the right side of 0.5 (training rows, so a plumbing check, not accuracy).
- `tests/test_steps_rain.py` with TabPFN active: 6/6 pass, 41 s for the whole file.
- Peak RAM during fit: not yet measured.

### 2026-10-26 T5 e-paper refresh time
- Setup: EE04 + 7.5" mono panel on Wi-Fi, firmware times its own refresh and reports it on `GET /`.
  Pushes sent with `POST /api/card/push` on the UNO Q (morning view), read back 8 s later.
- Trials: 5 pushes, plus the boot render.
- Result: full refresh 3186 / 3186 / 3187 / 3187 / 3188 ms; from the POST arriving to the panel done
  3189-3191 ms. Boot render 2989 ms. The app's push call answered in 339-483 ms (one at 2888 ms).
  Button presses: not yet measured. Power: not yet measured.

### 2026-10-26 T5 card offline
- Setup: `card_url` set to an address with no device (http://192.168.1.250), then a 1 min demo nap.
  State read from `/api/live` every 15 s for 240 s; `card_url` set back to http://192.168.1.7 afterwards.
- Trials: 1.
- Result: sunrise at 60 s, ringing at 120 s and still ringing at 240 s. The card push failed with
  ConnectionError and was shown as failed on the page; the alarm did not wait for it.

### 2026-10-26 T6 step splitting
- Setup: `tests/t6_steps.py` in the app container, Gemma 3 1B via llama-server, temperature 0. Five example
  jobs (made up for the test): tax return, garage, reply to landlord, back up photos, dentist.
- Trials: 5 jobs.
- Result: 4 sets of steps passed the checker (only numbers from the title, all three sizes, under 120 chars),
  1 fell back to the template (reply to landlord). 17.8-19.1 s per job.
  Quality misses the checker cannot catch: two "normal" steps restate the whole job ("Book a dentist
  appointment"), and the dentist steps are out of order ("Schedule a checkup" before "Find a dentist").
  Human "would you do this?" rating: not yet measured.

### 2026-10-26 T7 step size and predictor
- Setup: `tests/t7_predictor.py` in the app container with the venv python (TabPFN 2.2.1, CPU).
  No real mornings are logged yet, so the predictor data is synthetic: 120 mornings from a made-up rule
  (done when night score - 20 x size + weekend bonus > 50) with 10% labels flipped; 80 train, 40 held out.
- Trials: 6 cold-start cases; one fit + predict per backend.
- Result: cold-start rule 6/6 (score 40 and 69 -> tiny, 70 -> small, at 0 and at 19 rows; never normal).
  Held-out accuracy on the synthetic rows: TabPFN 0.82, logistic 0.80. TabPFN fit 15.3 s, predict 17.4 s
  (3 sizes per morning, once a day, off the alarm path); logistic 0.2 s / under 0.1 s.
  Accuracy on real mornings: not yet measured (needs 20+ labelled mornings).

### 2026-10-27 T0 radar accuracy
- Setup: radar wired to the board; radar breathing rate compared with a manual breath
  count, heart rate with a reference heart-rate reading.
- Trials: not recorded.
- Result: about 80-90% agreement. Movement gains (T1) still to be calibrated.

### 2026-10-27 T8 rain bonus
- Setup: INMP441 wired to the STM32 (SAI), rain bonus on.
- Trials: not recorded.
- Result: passed. Rain was detected and the alarm decision added +15 min.

### 2026-10-27 Chime
- Setup: tone on D3 -> PAM8403 -> small cavity speaker, wake alarm and test chime.
- Result: tested, working (checked by ear).

### Not yet measured
- T1 movement, T5 buttons and card power, T6 human rating, T7 accuracy on real mornings.
