# LFM1: Built-in model (LFM2.5-230M fine-tuned) on llama.cpp, Ollama optional

- **Engine.** `qwen_client.py` has two backends, chosen by `[qwen] backend`:
  - `llama` (default): `llama\llama-server.exe` (llama.cpp b12591, Vulkan build) with
    `models\lfm-hotkeys-Q6_K.gguf`. `ensure_llama()` starts it hidden and detached on 127.0.0.1:`llama_port`
    (8095) when `/health` does not answer, checks through `/props` that the server on the port is ours
    (otherwise: "Port … is used by another program"), and writes `work\llama-server.pid`. Requests go to
    the OpenAI-style `/v1/chat/completions` (streaming: server-sent events, `finish_reason` `length` →
    `TruncatedAnswer`, no end → `StreamIncomplete`). `--sleep-idle-seconds` follows `keep_alive`.
    `stop_llama()` (Free VRAM, `actions/unload.py`) kills only a pid whose image is `llama-server.exe`.
  - `ollama`: unchanged 1.1.0 code paths.
- **Prompts.** `prompt_loader` reads the backend itself and uses `prompts_lfm.py` for `llama`, `prompts.py`
  for `ollama` (`prompts_user.py` still overrides either). `prompts_lfm.py` holds the exact short prompts the
  model was trained on, without worked examples; follow-up questions reuse `prompts.followup_qa_messages`.
- **Other files.**
  - `websearch.ollama_ready()`: with `llama` it starts the engine (warm by the time the search ends).
  - `main.ahk`: neutral error texts, `StopLlama()` on exit and on Reload (a reload follows a settings
    change, so the next key restarts the engine with the new settings).
  - `settings.py` / `settings.html`: `qwen.backend`, `qwen.gpu`; Ollama-only fields hidden with `llama`.
  - `viewer.py` / `viewer.html`: messages no longer name Ollama.
- **Installer and build.** `build\pins.json` pins `llama_cpp` (zip, sha256 from the GitHub release digest)
  and `model` (the GGUF, sha256 of the maintainer's build). `build.ps1` puts `llama-server.exe` plus only the
  DLLs it loads into `app\llama\`, and the model into `app\models\`. `installer.nsi`: the Ollama section,
  `FindOllama`, `ollama-check.ps1` and the `MODEL` define are gone; `stop.ps1` also closes
  `<Dir>\llama\llama-server.exe`.
- **Licenses.** `licenses/llama.cpp/` (MIT, LLVM OpenMP), `licenses/lfm/` (LFM Open License v1.0 and the
  modification notice it requires); THIRD_PARTY_NOTICES §10–§11, `components.json` entries.
- **Tests.** `tests/test_llama_backend.py` (fake llama-server in `tests/support.py`); the Ollama tests pin
  `backend = ollama`.
- **Before a release.**
  - The model file must be attached to the release `model-lfm-hotkeys-v1` of this repository, the URL in
    `pins.json`, or the build cannot download it.
  - The model was trained in a separate lab (`C:\AI-Hotkeys-lab`, not in the repo). Results, see
    [docs/audit/model-choice-2026-11.md](../../audit/model-choice-2026-11.md).
- **Known gaps (model quality, not code).**
  - Explanations with long real web sources: 77% of the checks against 100% for Gemma 4 E4B; some answers
    repeat a line or skip the `[n]` citations.
  - Summaries sometimes misplace a detail (a wrong day); fixes sometimes change a verb's person.
  - "Organize into a bulleted list" as a follow-up edit is not followed.
