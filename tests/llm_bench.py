"""Time-to-first-token and tokens/s of the local llama-server (run on the board)."""
import json
import sys
import time
import urllib.request

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
PROMPT = "Say good morning in one short sentence."


def trial():
    body = json.dumps({"messages": [{"role": "user", "content": PROMPT}],
                       "stream": True, "max_tokens": 32, "temperature": 0}).encode()
    req = urllib.request.Request(URL + "/v1/chat/completions", body,
                                 {"Content-Type": "application/json"})
    t0, first, timings = time.time(), None, None
    with urllib.request.urlopen(req) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data:") or line.endswith("[DONE]"):
                continue
            d = json.loads(line[5:])
            timings = d.get("timings") or timings
            if first is None and d["choices"] and d["choices"][0]["delta"].get("content"):
                first = time.time() - t0
    return first, timings


if __name__ == "__main__":
    for i in range(3):
        ttft, t = trial()
        print(f"trial {i + 1}: ttft {ttft:.2f} s, prompt {t['prompt_n']} tok at "
              f"{t['prompt_per_second']:.2f} tok/s, generation {t['predicted_n']} tok at "
              f"{t['predicted_per_second']:.2f} tok/s")
