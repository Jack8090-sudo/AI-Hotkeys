# AI-Hotkeys — check that Ollama is running, recent enough, and has the model.
# Called by main.ahk at startup; on failure work/error.txt says what to do.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import qwen_client

if __name__ == "__main__":
    ok, message = qwen_client.health()
    print(message)
    if not ok:
        qwen_client.write_error(message, "health check")
    sys.exit(0 if ok else 1)
