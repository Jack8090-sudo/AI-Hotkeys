# AI-Hotkeys — libera la VRAM scaricando il modello da Ollama.
# Richiamato dal menu dell'icona nella barra delle applicazioni.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import qwen_client

if __name__ == "__main__":
    try:
        qwen_client.unload()
    except Exception as e:
        print(f"Errore: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)
