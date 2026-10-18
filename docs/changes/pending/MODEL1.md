# MODEL1: Default model Gemma 4 E4B (QAT), model-neutral texts

- **Default model.** It is now `gemma4:e4b-it-qat`, replacing `qwen3.5:9b`. It is set in these places, and
  `tests/test_settings_validate.py` `DefaultModelParityTest` keeps them in sync:
  - `qwen_client.DEFAULTS`
  - `settings.TEXTS`
  - `config.example.ini`
  - `installer.nsi` `MODEL`
  - the `settings.html` example
- **Other files changed:**
  - `tools/bench` defaults.
  - `ollama-check.ps1` already derives the manifest path from the name; only its comment changed.
- **Sampling.** `prompts.OPTIONS` uses `top_k` 64 and `top_p` 0.95 for every mode. Temperatures and
  `num_predict` are unchanged.
- **New explain prompts.** Text of 6 words or fewer gets a short explain prompt (`EXPLAIN_SHORT_SYSTEM`).
  `EXPLAIN_REST` gained a rule against repeating English phrases in parentheses.
- **Model-neutral texts.** User-visible strings say "the AI" instead of "Qwen". This covers `main.ahk`,
  `viewer.html`, `settings.html` (`query_mode` labels "AI or from the text" / "Only the AI's"), `viewer.py`,
  `websearch.py`, `obsidian_todo.py` and the installer. `obsidian_todo.ask_qwen` became `ask_model`.
- **Kept names (I11).** The `[qwen]` section and the `qwen_client.py` module keep their names. Both now
  carry a note that the name is historical.
- **Migration.** `config.ini` is never changed. The installer finish page, README, INSTALL, guide-it and
  TROUBLESHOOTING explain how to switch.
- **Evidence.** See [docs/audit/model-choice-2026-10.md](../../audit/model-choice-2026-10.md), measured with
  the new `tools/bench/model_eval.py`.
