# STREAM1: the first answer streams into the results page (E1, D7)

- **What changes for the user.** PgDn (summary), End (explanation) and PgUp outside a direct replace now
  open the results page at once. The first answer appears as it is written: first visible text in about
  1 s instead of waiting 2-26 s for the whole answer. Direct replace (PgUp in an editable app with
  `sostituisci_testo = si`) keeps the old non-streaming path, because it needs the whole text (I6, I15).
- **main.ahk / lib/Util.ahk.**
  - `ResultGoesToPage(...)` decides: page (stream) unless it is a direct replace.
  - `StartStreamPage` writes nothing new: it starts `viewer.py --run-dir=<dir> "<name>" <mode> "--key=…"
    --stream` (`ViewerCommand`) and waits, at most 10 s, until the page has taken the selection (it deletes
    `input.txt`). Then `busy` ends and the progress toast ("Opening the results page") closes. If the page
    does not start, the toast says so and the run folder is deleted.
  - **Esc 2 s (I5).** During that short wait the old path applies: the viewer is killed and the folder
    deleted. Afterwards AHK no longer owns the generating process. `CheckEscHold`, with no job of its own,
    calls `CancelStreams`, which writes a `cancel` file into every live streaming run folder
    (`streamDirs`, pruned with `LiveStreamDirs`). The page's server polls for it every 0.2 s, stops the
    answer (closing the Ollama stream stops generation) and deletes the folder. The page shows "Stopped
    before the answer" or keeps the text written so far, marked "Stopped here". A short Esc stays native.
    The flag file was preferred over "Esc inside the page" because it works whichever window has the
    focus. Stop and Esc inside the page work as well.
- **qwen_client.py: shared first-answer pipeline.** `run_action` and the page cannot drift:
  - `check_input` raises `ActionStop` (message, detail, exit code) when the selection is empty or longer
    than `max_input_chars`.
  - `first_sources` runs End's web search and returns the meta (`save=False` keeps the sources in memory).
  - `first_request_messages` is `prompts.first_messages` plus the sources block.
  - `finish_first` covers `done_reason = length`, `clean_answer`, the empty-answer case and `add_sources`.
  - `write_meta` writes `meta.json`, and `TRUNCATED_FIRST` is the cut-off message.
  - Only the network call differs: `chat_ex` versus `open_stream`, so the MODEL2 cloud guard covers both.
- **websearch.py.** One addition, `STATUS_HOOK`: when it is set, the progress phases go to it instead of
  `status.txt`.
- **viewer.py.**
  - The `--stream` option needs `--run-dir`. `load_run` reads `input.txt` and deletes it at once (S9). The
    folder stays only as the place for the cancel flag, and is deleted when the first answer ends (done,
    error or cancel), or when the server stops if the page never asked.
  - `FirstRun` holds the single-use state and `start_session` builds the session.
  - **`POST /api/first`** is token- and Host-checked like `/api/ask` and NDJSON:
    - `{"status"}` lines, then `{"t"}` pieces, then `{"done", "text", "meta"}`;
    - or `{"error"[, "partial"]}` with the K1 messages from `describe_error`, or `{"error", "cancelled"}`.
  - The pipeline (`first_answer_events`) runs in a worker thread, so a cancel is honoured at once, even
    while the server waits for the web or for Ollama.
  - Single use: a second call gets 409, so a reload never generates again.
  - `/api/ask` returns 409 until a first answer succeeded.
  - Deviation from the brief: `meta.json` is not written in stream mode. The meta goes in the `done` line
    and in memory, and the run folder is deleted right after, so the file would only add another copy on
    disk.
- **static/viewer.html.**
  - The selected text shows at once. The result area shows the status phases ("Checking whether a search
    is needed…", "Searching the web…", "Reading 3 pages…", "The AI is writing…"), then streams with the
    S10 throttled renderer.
  - When done it renders the final text (sources linked) and refreshes the header meta (searched words,
    "Ready in N s").
  - S10 accessibility is kept: `aria-busy`, "Answer ready." in the polite status, errors in the alert
    line, cut-off answers marked "Incomplete answer".
  - After an error or a stop the composer is locked ("To start again, select the text and press the
    hotkey").
  - I7 is unchanged: follow-ups, fix versions and changes, copy, sources.
  - The NDJSON reader is shared with the follow-ups (`readNdjson`).
- **Compatibility.** The old viewer forms (K3: `--run-dir` without `--stream`, and `<input> <output>`) and
  `actions/*.py` are unchanged. They are used by direct replace, by the "not pasted → results page"
  fallback, by the tests and by `tools/bench`.
- **Tests.**
  - `tests/test_first_stream.py` (24 tests): NDJSON order; final text and prompt identical to `run_action`
    in all three modes; single use; token; follow-ups only after the first answer; Ollama down, 404, too
    long (no request), empty, length and interrupted (partial), error field, cloud model refused; cancel
    flag during the answer (under 2.5 s while Ollama waits 3 s) and before the page asked; nothing left in
    `work\`; End with web search off and with FakeSearx + StaticPages (the S6a `_TEST_LOOPBACK_PORTS`
    seam), with the same text as `run_action`.
  - `tests/ahk/run.ahk` covers `ResultGoesToPage`, `ViewerCommand` and `LiveStreamDirs`.
- **Measured** (real Ollama 0.40.5, `gemma4:e4b-it-qat` warm, RTX 3060, 415-character text, 4 runs each,
  temp app copy, `web_search = false`):

  | Action | Viewer start → first piece (median / max) | POST → first piece (median) | Whole answer (median) |
  |---|---|---|---|
  | Summary | 0.36 s / 0.89 s | 0.11 s | 1.9 s |
  | Explanation | 0.35 s / 0.65 s | 0.08 s | 9.8 s |
  | Fix | 0.38 s / 0.59 s | 0.11 s | 1.6 s |

  In the built-in browser the result area was streaming 0.5 s after navigation started, with text
  painted by 0.8 s. There were no console or CSP errors.

## Manual checklist (Windows, before release)

1. PgDn on a paragraph in a browser: the page opens at once, the selected text is visible, and the summary
   streams with the caret. "Answer ready." and "Ready in N s" appear at the end.
2. End on a technical sentence with web search on: the status phases are visible ("Searching the web…",
   "Reading … pages…"). The answer has `[n]` citations and a Sources list, and the header shows the searched
   words. A follow-up uses the sources.
3. End with `web_search = false`: "Without web search" appears in the header.
4. PgUp in Notepad with `sostituisci_testo = si`: direct replace as before (progress toast, then paste; no
   page). PgUp in Chrome, or with `sostituisci_testo = no`: the page streams the fix. Versions, Changes and
   Copy work after it ends.
5. During a long explanation, hold Esc for 2 s in another window: the toast says "Cancelled", the page
   shows the text so far marked "Stopped here", and the composer is locked. `work\runs\` is empty.
6. Click Stop, and press Esc inside the page, while it streams: same result.
7. Press F5 on the page: the "Reload not available" banner appears and nothing generates again.
8. Stop Ollama, then press PgDn: the page shows "Ollama is not running…" as an alert.
9. Select more than the limit: the page shows "The selected text is too long…".
10. Press PgDn twice quickly on two texts: two pages stream independently. Holding Esc for 2 s stops both.
11. Close the tab before the first token: nothing is left in `work\runs\` after the answer ends (or after
    the 240 s idle shutdown).
12. Use a screen reader (NVDA): the status phases and "Answer ready." are announced politely, and errors
    are announced as alerts.
