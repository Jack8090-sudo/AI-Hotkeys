# MODEL2: Gemma by default, other local models optional, never cloud

- **Settings → Model is a picker.** `settings.py` asks Ollama `GET /api/tags` (qwen_client's no-proxy
  opener, the saved `ollama_url`, 2 s timeout) and builds `model_choices()`:
  - `recommended`: `gemma4:e4b-it-qat` (default), `gemma4:e2b-it-qat` (light), `gemma4:12b-it-qat`
    (maximum quality), each with `installed`.
  - `others`: the other installed local models, with size and quantization.
  - `cloud_hidden`: how many cloud models were left out.
  - `cloud_in_config`: a cloud name found in `config.ini`.
  - `reachable`: false when Ollama cannot be reached; the page then shows the current model read-only.
- **Page.** `static/settings.html` renders native radios in a `fieldset` with two labelled groups. Each
  radio is described by its status (`aria-describedby`), and the field has a hint, a note and an error.
  "Check installed models again" calls the new token-gated `GET /api/models`, because the page cannot be
  reloaded. No inline handlers and no external resources: the CSP is unchanged.
- **Validation (server side).** `settings.validate` keeps the name regex. It then calls `check_model`: a
  cloud name is always refused, a recommended name is always allowed, and any other name must be installed.
  With Ollama down, only recommended names pass. After saving a recommended model that is not downloaded,
  the reply carries `model_note` with the `ollama pull` command and fresh `models` data.
- **Runtime guard (`qwen_client.py`, kept small).**
  - `is_cloud_model(name)` checks for a `:cloud` / `-cloud` suffix.
  - `load_config` replaces a cloud model with the default and adds a K6 warning.
  - `health()` refuses a cloud model, including an `/api/tags` entry with `remote_host` / `remote_model`.
  - `_request` raises `CloudModelRefused`, so the action path writes the K1 line "Cloud models are not
    allowed: AI-Hotkeys keeps your text on this PC. Choose a local model in Settings."
- **Config (I11).** The key stays `[qwen] model`, and no key or value changed. `current_values()` shows a
  cloud value as the default.
- **Tests.** `tests/test_settings_models.py` covers the picker data, validation, the Ollama-down fallback,
  `/api/models`, the save reply and the runtime refusal. `FakeOllama` gained a configurable `models` list.
- **Checked by hand** against the real Ollama (`gemma4` e4b/e2b/12b and `qwen3.5:9b`) from a temp copy. The
  picker showed correctly, with no CSP errors. Arrow keys moved the selection, and Tab, Enter and Save worked
  with the keyboard. A cloud save got a 422, and the Ollama-down view worked.
