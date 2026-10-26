# Measurements

Every number in the README comes from this file. Each entry: date, setup, trials, result.
Anything not tested yet says "not yet measured".

| ID | What | Result |
|---|---|---|
| B0 | Board baseline, LLM time to first token and tokens/s | 2.38 s first token (cold prompt); 4.42-4.45 tok/s generation; 6.5-7.4 tok/s prompt |
| T0 | Breath / heart rate vs manual count | not yet measured |
| T1 | Movement detection | not yet measured |
| T2 | Bridge rows, drops, max message size | partial: 12 injected lines + 1 malformed -> one row, lines=12 bad=1; long run not yet measured |
| T3 | Alarm decision and health limits (unit tests) | 12/12 cases pass |
| T4 | Wake message validation and generation time | 10 records: 8 valid first try, 2 after retry, 0 template; 20.3-37.9 s per message |
| T4b | Demo nap end to end | not yet measured |
| T5 | E-paper card refresh, latency, offline behaviour, buttons | not yet measured |
| T6 | Step splitting | not yet measured |
| T7 | Step size choice, predictor fit/predict time | not yet measured |
| T8 | Rain classifier | not yet measured |

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
  Long-run drop rate and real radar traffic: not yet measured.

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

### Not yet measured
- T5 e-paper refresh time and power, T6/T7 step completion and predictor accuracy, T8 rain detection.
