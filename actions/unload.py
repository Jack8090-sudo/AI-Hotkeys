# AI-Hotkeys — free VRAM by unloading the model from Ollama.
# Called from the taskbar tray-icon menu.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import qwen_client

if __name__ == "__main__":
    try:
        qwen_client.unload()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        qwen_client.write_error(*qwen_client.describe_error(e))
        sys.exit(1)
    sys.exit(0)
