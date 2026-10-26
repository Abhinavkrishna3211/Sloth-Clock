# Sloth Clock

A bedside sloth that wakes you gently and moves the jobs you keep putting off forward, one tiny step a day.

- **Sleeps-in for you, safely.** A 60 GHz mmWave radar watches breathing, heart rate and restlessness — no camera,
  no wearable. After a bad night (or a rainy morning) it gives up to 30 extra minutes, never past your
  "must be up by" time. No snooze. You wake to a sunrise on the LED matrix and a soft chime.
- **Remembers for you.** A no-glow 7.5" e-paper card shows tomorrow's alarm and the next important dates.
- **One tiny step a day.** Jobs you keep postponing are split into small steps. After a poor night it asks for the
  tiniest step; after a good night, a little more. It learns which step size you actually finish.

Everything runs offline on an Arduino UNO Q.

## Status
Work in progress. Measured results: `docs/measurements.md`. Progress: `docs/progress.md`.

- Radar logging, night score, alarm decision with health limits, LED-matrix sunrise, chime, wake message
  and validator: running on the board.
- Backup alarm on the MCU (rings on its own if Linux misses the alarm), dates and postponed jobs,
  one tiny step a day, rain features, e-paper card: written, unit tests pass; not yet tested on hardware.
- Step size predictor: uses TabPFN when it is installed on the board, otherwise a small logistic
  regression in numpy. Until 20 mornings are logged a fixed rule picks the size. TabPFN is not installed yet.

## Hardware
- Arduino UNO Q (4 GB)
- Seeed MR60BHA2 60 GHz mmWave breathing & heartbeat sensor (on its XIAO ESP32C6 kit)
- Seeed XIAO ePaper Display Board EE04 + 7.5" monochrome ePaper (800×480)
- INMP441 I2S microphone (rain detection)
- Push button, small speaker

## How it works
- **STM32 (real time):** radar frames, rain sound features, LED-matrix face and sunrise, chime, button.
- **Linux (on the same board):** sleep score, alarm decision with hard health limits, step-size predictor,
  Gemma 3 1B (llama.cpp) for the wording, with every number it writes checked against the measurements.

## Privacy
No audio or raw radar data is stored or sent anywhere. Only small feature rows and events are kept, on the board.

## Health limits
Max +30 minutes, never past your hard limit, no snooze, no shifting two days in a row unless the night was very poor.
This is a comfort device, not a medical one.

## Safety
Low voltage (USB) only. No mains wiring.

## Credits
- llama.cpp, Gemma 3 (Google), Seeed mmWave and Seeed_GFX libraries, ArduinoJson, TabPFN (Prior Labs, optional), numpy.

## License
MIT
