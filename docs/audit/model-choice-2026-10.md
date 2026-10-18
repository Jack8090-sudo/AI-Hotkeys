# Default model choice — October 2026

- **Decision:** the default model becomes `gemma4:e4b-it-qat` (Gemma 4 E4B, quantization-aware trained),
  replacing `qwen3.5:9b`. Version 1.1.0.
- **Tool:** `tools/bench/model_eval.py` (not shipped). Raw output goes to `tools/bench/out/`, which is gitignored.
- **Machine:** the same as [baseline-2026-10.md](baseline-2026-10.md): RTX 3060 12 GB, Ollama 0.40.5.

## Result

| Model | Pass | Speed | Median VRAM | Notes |
|---|---|---|---|---|
| `qwen3.5:9b` | 79.5% | 55 tok/s | 5.7 GB | Obsidian To-Do 0/2: duplicated a task |
| `gemma4:e4b-it-qat` (QAT, 6.1 GB download) | 98.5% | 75 tok/s | 3.1 GB | about 2× faster per task; the only miss is an arguable "Da fare" omission |
| `gemma4:e2b-it-qat` (QAT, 4.3 GB download) | 98.5% | 129 tok/s | 1.7 GB | about 2× faster than e4b; explanations noticeably shallower; its one miss added a "Da fare" bullet to an article with no tasks |
| `gemma4:12b-it-qat` | 100% | 41 tok/s | 7.4 GB | about 2× slower than e4b |

- **Why E4B and not 12B.** 12B passes everything, but it takes about twice as long per task and needs more
  than twice the VRAM. E4B's one miss is debatable, so for a hotkey tool the speed gain is worth more.
- **Why E4B and not E2B.** E2B has the same pass rate and is about twice as fast, but its explanations are
  noticeably shallower: about 1,000–2,500 characters with fewer details, against about 2,000–3,000 for E4B.
  The checks do not measure depth, so the pass rate hides this. E2B is the recommended **light** option
  for GPUs with 4 GB or less, or for CPU-only PCs. `gemma4:12b-it-qat` is the option for maximum quality.
- **Known E4B quirk.** With an English source, explanations sometimes repeated short English phrases in
  bold parentheses, for example "(**locally**)" or "(**that client only**)". It was cosmetic and was not
  counted as a failure. `EXPLAIN_REST` in `prompts.py` now says not to repeat English words or phrases in
  parentheses, keeping only technical terms in the original. After that rule, no echo appeared in the
  9 explanation answers checked (3 × technical, English source, web sources). The only parentheses left
  held Italian glosses or technical terms such as `TTL` and `client`.
- **Why not Qwen any more.** Qwen is the slowest per task, uses almost twice the VRAM of E4B, and failed
  the Obsidian To-Do reorganization. That check guards the user's real file.
- **Hardware.** About 3–4 GB of VRAM with the app's 16K context, so 8 GB cards fit comfortably and 6 GB
  cards likely work. Before, an 8 GB card was the minimum and 12 GB was recommended.
- **License.** Google releases Gemma 4 under the Apache License 2.0
  (<https://ai.google.dev/gemma/apache_2>). The older Gemma Terms of Use
  (<https://ai.google.dev/gemma/terms>) apply to Gemma 1–3 only. Ollama's model page also lists Apache 2.0.

## Method

- **Tasks.** 22 synthetic cases built from the app's own prompts (`prompts.py` through `prompt_loader`):
  - 8 PgUp fixes: typos, accents, informal text with emoji, a Markdown list, English to Italian, text that is
    already correct, code that must stay unchanged, and a prompt injection.
  - 1 PgUp follow-up ("make it more formal").
  - 2 summaries: an article, and an email with tasks.
  - 5 explanations: technical text, an English source, a negation trap, a single word (the new short-text
    prompt), and an explanation with web sources and citations.
  - 5 search decisions: three texts that need no search, one API question, and a forced error message.
  - 1 Obsidian To-Do reorganization, validated by the app's own `obsidian_todo.validate`.
- **Checks.** These are automatic, per case. Examples: no chatty intro, length ratio to the source,
  Italian output, required words kept, no invented facts, valid `[n]` citations, `NO` for a personal note,
  queries without file names. The answer is cleaned with `qwen_client.clean_answer`, as in the app.
- **Options.** These match the app: `think: false`, `num_ctx` 16384, and each mode's `prompts.OPTIONS`.
  `--options` overrides them per mode for experiments.
- **Repetitions.** 3 per model. The model is unloaded first and warmed with one short request, and the
  VRAM is read from `/api/ps`.
- **Speed.** This is Ollama's `eval_count / eval_duration`, median over all runs. "Per task" compares total
  wall time.

Reproduce:

```
python tools/bench/model_eval.py --models qwen3.5:9b gemma4:e2b-it-qat gemma4:e4b-it-qat gemma4:12b-it-qat --rep 3
```

## Final run (shipped configuration)

This run used `gemma4:e4b-it-qat` with the shipped `prompts.py`: `top_k` 64 / `top_p` 0.95 in
`OPTIONS`, the new short-text explain prompt and the English-echo rule. All modes, 3 repetitions, same
machine (2026-10-18):

| Mode | Pass | Mean time per task |
|---|---|---|
| PgUp fix (incl. follow-up) | 27/27 | 0.67 s |
| Summary | 6/6 | 2.32 s |
| Explanation | 15/15 | 4.60 s |
| Search decision | 15/15 | 0.26 s |
| Obsidian To-Do | 3/3 | 3.59 s |
| **Total** | **66/66 (100%)** | 115.5 s for all 66 |

Median speed was 76.7 tok/s, VRAM 3.07 GB, and the cold load took 6.3 s. The "Da fare" miss from the
comparison run did not recur.

## Sampling

Gemma 4's recommended sampling is `top_k` 64 and `top_p` 0.95. The best measured setting keeps the app's
low temperatures (0.2–0.5) for the fidelity tasks and adds `top_k` 64 / `top_p` 0.95. That is now the
setting in `prompts.OPTIONS` for every mode. `num_predict` is unchanged. Gemma 4 can think before
answering, so `think: false` still applies and is still sent with every request.

## Existing users

An upgrade never rewrites `config.ini`, so it keeps `model = qwen3.5:9b`. To switch, run
`ollama pull gemma4:e4b-it-qat` and set Settings → Model. If the configured model is missing, the startup
health check says "Model X not found: run ollama pull X". The installer finish page, README, INSTALL and
CHANGELOG explain the switch. Nothing changes the user's config on its own.
