# AI-Hotkeys — check the AI engine: built-in llama-server (started now, so the first key is fast),
# or Ollama (running, recent enough, model present).
# Called by main.ahk at startup; on failure work/error.txt says what to do.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import qwen_client

if __name__ == "__main__":
    qwen_client.report_config_warnings()
    ok, message = qwen_client.health()
    print(message)
    if ok:
        qwen_client.clear_error()
    else:
        qwen_client.write_error(message, "health check")
    sys.exit(0 if ok else 1)
