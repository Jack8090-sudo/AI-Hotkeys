# AI-Hotkeys — azione "explain". I prompt sono in prompts.py.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import qwen_client

if __name__ == "__main__":
    sys.exit(qwen_client.run_action("explain", sys.argv))
