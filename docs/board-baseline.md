# Board baseline (Arduino UNO Q, 4 GB)

Captured 2026-10-26.

- Arduino App CLI 0.11.0; app image python-apps-base 0.10.1 (Python 3.13).
- llama.cpp llama-server 0.6.0-dev (build 11449, commit 65840ed53), built for Linux aarch64.
- Model: `~/models/gemma-3-1b-it-qat-Q4_0.gguf`, served on port 8080 by the user service in
  `deploy/llama-server.service` (starts at boot).
- Root disk: 9.8 G, 4.4 G free. RAM: 3667 MB total, 3083 MB available with the app and the model running.
- Default app: Sloth Clock (starts at boot).
