# Performance baseline and runtime hypotheses — October 2026 (S3)

- **Plan step:** S3 of `plans/ai-hotkeys-production-readiness.md`
- **Measured:** 2026-10-17, one machine, no application code changed.
- **Tools:** `tools/bench/` (not shipped). Raw output goes to `tools/bench/out/`, which is gitignored.
- **Rule for later steps:** state thresholds relative to these numbers. Re-measure on the same machine with the same tools, using interleaved runs and reporting median and p90.

## 1. Environment manifest (redacted)

| Item | Value |
|---|---|
| OS | Windows 11 Pro, build 26200, x64 |
| CPU / RAM | AMD Ryzen 7 5700X (8 cores), 32 GB |
| Storage | NVMe SSD |
| GPU / VRAM | NVIDIA GeForce RTX 3060, 12 GB (12288 MiB) |
| NVIDIA driver | 617.42 |
| Ollama | 0.40.5 (llama.cpp runner, `n_slots = 1`, `n_ctx_slot = 16384`) |
| Model | `qwen3.5:9b`, Q4_K_M, 6.55 GB, digest `56671c2ab938…0179a3c90` |
| App interpreter | bundled `python\python.exe` 3.13.7 (the app itself launches `pythonw.exe` from the same folder) |
| App config used | temporary `config.ini`: `keep_alive = 30m`, `lunghezza = normale`, `web_search = false` unless a section says otherwise |

**Caveat: the machine was not quiet.** Other agents were running test suites in parallel worktrees during the CPU-bound measurements, so the fake-pipeline numbers include some CPU contention. The GPU-bound numbers (model time) are unaffected: generation speed stayed at 53–56 tok/s in every run.

## 2. Method

- **Isolation.** Every run uses a temporary copy of the app (root `*.py`, `actions/`, `static/`) with its own `config.ini` and `work/`. The real `config.ini`, the real `work/` and the user's SearXNG on port 8888 were never touched.
- **Bytecode.** Child processes write bytecode to a private `PYTHONPYCACHEPREFIX`. One warm-up round fills it, so the measured runs see the steady state of a real install, which already has its `__pycache__`.
- **Interleaving.** Phases alternate inside each repetition, A B C then C B A, so drift and order effects cancel out.
- **Recording proxy (`tools/bench/proxy.py`).** It sits between the app and Ollama. Per request it records TTFB, TTFT, total time and Ollama's final-chunk stats (`load_duration`, `prompt_eval_*`, `eval_*`, `done_reason`), but no message text. It propagates client disconnects upstream.
- **Corpus (`tools/bench/corpus.py`).** Fixed, synthetic Italian text in three sizes per action:

  | Size | Target | Actual characters |
  |---|---|---|
  | S | about 400 | rewrite 400, summarize 209, explain 242 |
  | M | about 2000 | 1770, 1518, 1977 |
  | L | about 6000 | 5862, 5445, 5961 |

  No user documents were used.
- **"Overhead".** This is the action process wall time minus the proxy's time for the Ollama call. It covers interpreter start-up, imports, config, file I/O and the HTTP hop.

Commands:

```
python tools/bench/run.py --fake --n 20          # pipeline overhead, FakeOllama
python tools/bench/run.py --real                 # cold 3 + warm 10 + stream 3, through the proxy
python tools/bench/h04_viewer_race.py --reps 10  # H04 (fake)
python tools/bench/h08_cancel.py                 # H08 (real Ollama, direct)
python tools/bench/h11_truncation.py             # H11 (real Ollama, proxy)
python tools/bench/explain_split.py --searxng    # explain phase split + H23
ahk\AutoHotkey64.exe tools\bench\clipwait_probe.ahk   # manual: ClipWait latency per app (D12/H07)
```

## 3. Pipeline overhead (FakeOllama, no model)

Two independent runs of `run.py --fake --n 20`. All values are in milliseconds.

| Phase | Run 1 median | Run 1 p90 | Run 2 median | Run 2 p90 | Median Δ |
|---|---|---|---|---|---|
| Interpreter start-up (`-c pass`) | 69.3 | 86.8 | 66.8 | 86.4 | −3.6 % |
| Start-up with `-E -s` (D2) | 66.3 | 127.3 | 67.5 | 95.0 | +1.8 % |
| `import qwen_client` (incl. start-up) | 223.1 | 315.3 | 219.6 | 319.3 | −1.6 % |
| `import websearch` (incl. start-up) | 247.9 | 283.0 | 259.6 | 365.1 | +4.7 % |
| `curl_cffi` import (incl. start-up) | 319.8 | 462.5 | 300.9 | 355.1 | −5.9 % |
| Action end to end, rewrite (M) | 247.5 | 328.2 | 232.7 | 319.9 | −6.0 % |
| Action end to end, summarize (M) | 235.6 | 339.9 | 235.5 | 292.9 | 0.0 % |
| Action end to end, explain (M, no web) | 266.2 | 359.4 | 256.2 | 308.3 | −3.8 % |
| Viewer spawn → URL printed | 255.6 | 308.8 | 254.1 | 302.4 | −0.6 % |
| Viewer spawn → first page byte (TTFB) | 269.2 | 322.1 | 271.9 | 328.6 | +1.0 % |

**Reproducibility.** Every median is within ±6 % between the two runs, which meets the ±10 % acceptance criterion.

Reading the numbers:
- An action's whole non-model cost is about 0.23–0.27 s. Most of it is interpreter start-up (about 70 ms) plus the `qwen_client` import chain (`urllib.request`, `http.client`, `email`, `configparser`, `prompt_loader`). These figures are higher than the earlier audit's 90/140 ms estimates because of the CPU contention noted in §1.
- `-E -s` does not change start-up measurably on the bundled interpreter.
- E9 (pre-importing `curl_cffi`): the import costs about 80–100 ms beyond `import websearch`. It only applies when a web search actually runs.

## 4. Real model (`qwen3.5:9b`), through the proxy, `web_search = false`

**Runs.** Cold: 3 repetitions per action and size, with the model unloaded through `actions/unload.py` before each run and `/api/ps` empty confirmed. Warm: 10 repetitions after one unrecorded warm-up. All 126 runs exited with code 0 and `done_reason = stop`.

### 4.1 Wall time of the action process (what the user waits for before the page or replace)

| Action / size | Cold median | Cold p90 | Warm median | Warm p90 | Warm overhead median (p90) |
|---|---|---|---|---|---|
| rewrite S | 7.85 s | 8.13 s | **1.96 s** | 2.03 s | 0.22 s (0.25) |
| rewrite M | 10.74 s | 10.92 s | **4.62 s** | 4.77 s | 0.22 s (0.25) |
| rewrite L | 25.11 s | 25.96 s | **18.19 s** | 19.04 s | 0.21 s (0.26) |
| summarize S | 7.67 s | 7.72 s | **1.38 s** | 1.99 s | 0.22 s (0.24) |
| summarize M | 11.63 s | 13.92 s | **5.02 s** | 5.64 s | 0.22 s (0.24) |
| summarize L | 11.31 s | 12.28 s | **4.90 s** | 5.73 s | 0.21 s (0.24) |
| explain S | 16.01 s | 16.67 s | **10.15 s** | 12.37 s | 0.24 s (0.27) |
| explain M | 31.42 s | 31.70 s | **25.74 s** | 28.99 s | 0.26 s (0.28) |
| explain L | 33.78 s | 34.29 s | **26.30 s** | 27.99 s | 0.24 s (0.28) |

### 4.2 Ollama phases (medians)

| Action / size | Prompt tokens | Generated tokens | Cold load | Prompt eval, cold | Generation | Speed |
|---|---|---|---|---|---|---|
| rewrite S | 497 | 80 | 5.65 s | 0.34 s | 1.43 s | 56 tok/s |
| rewrite M | 795 | 227 | 5.86 s | 0.50 s | 4.06 s | 56 tok/s |
| rewrite L | 1686 | 990 | 5.81 s | 0.94 s | 17.9 s | 55 tok/s |
| summarize S | 447 | 47–50 | 5.91 s | 0.33 s | 0.85 s | 54 tok/s |
| summarize M | 725 | 234–242 | 6.23 s | 0.46 s | 4.39 s | 53 tok/s |
| summarize L | 1559 | 222–230 | 5.84 s | 0.87 s | 4.32 s | 53 tok/s |
| explain S | 814 | 531–549 | 5.57 s | 0.50 s | 9.6 s | 56 tok/s |
| explain M | 1185 | about 1390 | 5.03 s | 0.70 s | 25.1 s | 55 tok/s |
| explain L | 2047 | 1430–1490 | 5.52 s | 1.09 s | 25.9 s | 55 tok/s |

Findings:
- **Prompt eval.** Cold prompt evaluation runs at about 1,400–1,900 tok/s. Warm runs reuse Ollama's prompt cache because the corpus repeats identical text, so warm prompt eval (0.05–0.7 s) is optimistic. For a fresh selection, expect the cold prompt-eval figure.
- **Cold load.** The cold-load penalty is about 5–6 s when the model files are in the OS cache. The very first load after a long idle (smoke run) took 14.7 s of load plus 39 s of first prompt evaluation for 497 tokens, a one-off GPU or driver warm-up. Real "first press of the day" latency can therefore reach about 55 s.
- **Generation dominates every warm run.** At 53–56 tok/s, explain is long because the four-section answer is 500–1,500 tokens.
- **Tokens per character.** Italian prose measures about 4.4 characters per token (45,000 chars → 10,093 tokens). `max_input_chars()` assumes 3, so its limits are conservative (see H11).

### 4.3 Streaming the first answer (E1 / D7)

This probe makes the same first request with `stream = true`, warm, size M, 3 repetitions.

| Action M | TTFT median | Total median |
|---|---|---|
| rewrite | 0.15 s | 4.43 s |
| summarize | 0.12 s | 4.77 s |
| explain | 0.15 s | 23.14 s |

These TTFTs are cache-assisted. For a fresh selection, TTFT ≈ prompt eval ≈ 0.3–1.1 s on a warm model. **Recommendation for D7:** streaming would cut the wait for the first visible text from 5–26 s to under about 1 s for summarize and explain. It is by far the largest perceived-latency lever, an order of magnitude more than any process-level optimisation.

### 4.4 Explain phase split (`web_search = auto`)

Synthetic texts: `tech_S` and `tech_M`, where technical terms force a search, and `personal`, a personal note where the model decides. The fake-SearXNG pass (5 repetitions) has no internet traffic and returns no results. The real-SearXNG pass ran 1 repetition on a free alternate port with a temporary `--work-dir`; it found 5 sources for the technical texts.

| Pass / text | Wall | Query-decision call | Search + fetch + rest | Answer call |
|---|---|---|---|---|
| fake / tech_S | 11.85 s (p90 14.30) | 0.57 s (0.61) | 0.49 s | 10.82 s |
| fake / tech_M | 28.11 s (p90 29.23) | 1.22 s (1.62) | 0.54 s | 26.35 s |
| fake / personal | 6.42 s (p90 7.35) | 0.22 s (0.40) | 0.32 s | 5.89 s |
| real / tech_S | 21.11 s | 0.88 s | 2.76 s | 17.47 s (3,030 prompt tokens) |
| real / tech_M | 37.91 s | 1.29 s | 2.52 s | 34.11 s (3,826 prompt tokens) |
| real / personal | 5.22 s | 0.21 s | 0.33 s | 4.68 s (no search) |

**Reading.** With real sources, the answer call grows by about 7–8 s, from the larger prompt (about +2,200–2,600 tokens) and a longer answer. Search plus page fetch adds about 2.5–2.8 s. The decision call costs 0.2–1.3 s.

## 5. Hypothesis status

| ID | Status | Evidence |
|---|---|---|
| H02 | **Needs manual verification** | Requires desktop interaction; see §6.1. |
| H03 | **Needs manual verification** | Requires Explorer; see §6.2. Code review: `ClipWait(2)` with no argument waits for text *or files*, and `A_Clipboard` then holds the file paths, so the paths would become the "selected text". The probe records `kind=files`. |
| H04 | **Confirmed** | `h04_viewer_race.py`, fake Ollama, synthetic text. A second run started *d* ms after the viewer spawn gives the outcomes below. Viewer 1 reads `input.txt`/`output.txt` 200–300 ms after spawn (§3). Run 2 deletes `output.txt` in that window, so viewer 1 dies with an uncaught `FileNotFoundError`. It runs hidden, so the user sees nothing: a silent crash, and run 1's result is lost. A mismatched A/B pair was not observed, because the viewer reads the two files back to back. Fix belongs to S9. |
| H05 | **Refuted on this machine** (Store alias untested) | `where pythonw` → one real per-user CPython 3.13 install, with no `pyvenv.cfg` and no WindowsApps `pythonw` alias. The bundled `python\pythonw.exe` exists, so `FindPython()` uses it and PATH is never consulted. Process-tree test: the bundled and per-user `pythonw.exe` run the script in-process (no child). A CPython 3.13 **venv** `pythonw.exe` starts a child interpreter, but killing the launcher PID also ended the child within 0.8 s (the launcher holds it in a kill-on-close job), so Esc still stops the work. A Microsoft Store `pythonw` alias was not present and is untested. |
| H06 | **Needs manual verification** | See §6.3. |
| H07 | **Needs manual verification** | See §6.4. `tools/bench/clipwait_probe.ahk` measures the copy latency per app exactly like `RunSelectionAction`. |
| H08 | **Confirmed** | `h08_cancel.py`, real Ollama, direct connection as in production, action killed with TerminateProcess like `ProcessClose`. Three cases below. In all three, GPU utilisation fell from 94–100 % to 1–2 %, and a 1-token probe was served in 0.15–1.0 s, while Ollama runs a single slot. Uninterrupted reference: 17.1 s. |
| H11 | **Refuted for the app's first requests; Ollama behaviour confirmed** | `h11_truncation.py`, through the proxy. Four observations below. Residual risk: the follow-up paths in the viewer (history plus original plus result) have no such guard. S4/S7 should compare `prompt_eval_count` with the expected size, or guard follow-up input. |
| H22 | **Refuted** (a persistent worker would not cut latency meaningfully) | Warm rewrite S is 1.96 s, M 4.62 s. The whole process overhead a worker could remove is 0.21–0.26 s (start-up about 70 ms plus imports about 150 ms): 11 % of the smallest rewrite and ≤ 5 % of anything larger. Generation is 62–98 % of every warm run. Streaming (§4.3) is the better lever. |
| H23 | **Timing: skip not worth it. Quality: inconclusive** | The decision call costs 0.57 s (tech_S) and 1.22 s (tech_M) of 11.9 / 28.1 s, i.e. 4–5 % of explain. The fallback query for forced searches would be the raw term list. The model's queries combine the terms into targeted searches (see below), which is likely better retrieval. A full answer-quality comparison needs real search on both variants and human judgment. Recommendation: keep the call. |

H04 outcomes by delay *d* (10 repetitions per delay unless noted):

| Run-2 model delay | d = 0–25 ms | d = 50–150 ms | d = 200–300 ms | d ≥ 300–400 ms |
|---|---|---|---|---|
| 0 s | viewer 1 shows **run 2's pair**, B/B (7–9 of 20 per run), or crashes | **100 % crash** | mixed crash / correct | 100 % correct |
| 1 s (5 repetitions per delay) | crash | crash | crash up to 200 ms, mostly correct at 250 ms | 100 % correct from 300 ms |

H08 cases:

| Case | Server log | Probe and GPU |
|---|---|---|
| Kill at 2 s during prefill (summarize, 34k chars, 7,968 prompt tokens) | `stop: cancel task`, slot released at 5,120 of 7,968 tokens: prefill aborted after the current batch | Probe waited 1.0 s |
| Kill at 2 s, early generation (rewrite, 7.6k chars) | Cancelled at 2,143 tokens: 2,066 prompt + 77 generated | — |
| Kill at 10 s, mid-generation (same rewrite) | Cancelled at 2,575 tokens: about 509 generated, against about 1,000 for a full answer | Probe 0.15 s |

H11 observations:

1. The app's own guard stops a 45,000-character selection before Ollama is called. The summarize action exits with code 3 and the message "too long (45,000 characters, about 37,008 at most)". No request reached Ollama.
2. Bypassing the guard, 45,000 characters is 10,093–10,443 tokens and **fits** in `num_ctx = 16384`, with no truncation. A canary system prompt was obeyed.
3. At 75,000 characters (16,843–17,193 tokens) Ollama 0.40.5 **silently truncates**. The server log shows `truncating input prompt limit=8194 … keep=4 new=8194`, which keeps only the first 4 tokens and the last half of the context. The response is HTTP 200 with `done_reason = stop`, and `prompt_eval_count` is 8,194. The canary system prompt was lost: the answer no longer started with the canary word, and the app's summary started with "Ecco un riassunto…", a sign its instructions were dropped.
4. The app's 3-chars-per-token estimate is conservative (measured about 4.4), so the guard leaves margin.

H23 queries:

| Text | Fallback (raw technical terms) | Model's queries |
|---|---|---|
| tech_S | "API REST TTL JWT" | "Nginx REST API reverse proxy", "JWT token bypass cache TTL" |
| tech_M | — | "PostgreSQL connection pool HTTP 503 PgBouncer" |
| personal | — | NO, correctly, with no search |

## 6. Manual procedures (needs manual verification)

Before any of these:
1. Quit AI-Hotkeys from the tray.
2. Start the probe: `ahk\AutoHotkey64.exe tools\bench\clipwait_probe.ahk`. Ctrl+Alt+F11 probes the copy; Ctrl+Alt+F12 quits.
3. Results go to `tools\bench\out\clipwait.csv`: process name, ms, character count, ok, kind. No copied text is written.

For the tests that need the full app (H02 and H03 with the fake), start a temporary copy instead of the live app:
1. Copy the repo to a temp folder.
2. Give it a `config.ini` whose `ollama_url` points at `python tools/bench/proxy.py --port 11500 --upstream http://127.0.0.1:<FakeOllama port>`. For simplicity, a real Ollama behind the proxy also works.
3. Run `ahk\AutoHotkey64.exe main.ahk` from that copy.

### 6.1 H02: `^c` with no selection in console programs
1. Open Windows Terminal and run `ping -t localhost`.
2. Make sure nothing is selected, then press the probe hotkey, and then (with the temporary app copy running) PgUp.
3. **Confirmed** if `ping` stops ("Control-C" printed) or the console exits. **Refuted** if `ping` keeps running.
4. Repeat in classic conhost (`conhost.exe cmd`) and in a PowerShell window. Record the result per host.
5. Note the probe's `ok = 0` row. Its ms value is the full ClipWait timeout the user waits before the key's native function runs (C03).

### 6.2 H03: file selection in Explorer
1. Select two files on a scratch folder in Explorer and press the probe hotkey. `kind = files` with `chars > 0` shows that paths would be captured.
2. With the temporary app copy and the proxy, press PgDn on the selection. **Confirmed** if the proxy log shows a `/api/chat` request whose `prompt_chars` is about the length of the paths plus the prompt. Use only synthetic file names.

### 6.3 H06: elevated windows (UIPI)
1. Run Notepad as administrator and type some text. Select it, then press the probe hotkey.
2. **Confirmed** if the probe reports "nothing copied within 5 s" (`ok = 0`) while the same test in a normal Notepad succeeds.
3. Then try PgUp with the temporary app copy. Expected if confirmed: the native PgUp after 2 s, no result. Document only; no fix is planned.

### 6.4 H07 and the D12 data: ClipWait latency per app
With the probe, select and copy at least 10 times in each of:
- Notepad, Word, VS Code, Obsidian, Chrome (page text and a textarea)
- Excel, with a 10-cell range and with a 50,000-cell range
- an RDP session window, where you select inside the remote desktop

Also copy once with nothing selected in each app; that row shows the full timeout.

Report the median, p99 and max ms per app. **H07 is confirmed** if any app's max exceeds 2,000 ms or the copy fails (`ok = 0`) with a selection present.

## 7. Recommendation for D12 (ClipWait timeout)

Nothing about clipboard latency could be measured automatically: it needs a real foreground app with a real selection. **The data is inconclusive, so per D12 the 2 s default stays.**

Once §6.4 has been run:
- set the default to `max(500 ms, 3 × p99 of the slowest common app)`, rounded up to 100 ms;
- keep `clip_wait_ms` as an optional key for Excel and RDP users;
- if Excel or RDP exceed 2 s, keep 2 s as the default and document the key.

What is known now: the non-selection case always costs the full timeout (C03), currently 2 s. In comparison, a warm summarize S takes 1.4 s and a warm rewrite S 2.0 s, so the press with nothing selected is as slow as a real short action.

## 8. Thresholds for later steps (relative to this baseline)

- **Process overhead.** Any change touching the action start-up or imports must keep the fake-pipeline action median within +10 % of §3: about 0.26 s for each action, and viewer TTFB about 0.27 s.
- **Model behaviour.** Warm-model changes such as prompt edits or `num_predict` must report generated tokens and wall time against §4.1/§4.2 on the same corpus.
- **E1 streaming, if adopted.** The target is first visible text within the warm prompt-eval time plus 0.3 s, for every action.
