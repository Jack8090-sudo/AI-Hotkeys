# Privacy

AI-Hotkeys is built to keep your text on your PC. This page lists exactly what stays local, what can
leave your PC, and when your text is deleted.

## No telemetry

AI-Hotkeys has no telemetry, analytics, update checks or crash reporting. It never contacts the project
or any server of its own. The only network traffic it creates is described below.

## What stays on your PC

- **Your selected text and the answers.** PgUp, PgDn and End send the selection to Ollama at `ollama_url`,
  by default `http://localhost:11434`, which is Ollama running on your own PC. The model runs locally.
  Ollama requests deliberately bypass any system proxy, so they cannot be routed through a corporate proxy.
- **The results and Settings pages.** They are small servers on `127.0.0.1` that only your PC can reach.
  The pages do not load anything from the internet: fonts and scripts are local, and remote images in an
  answer are shown as a link ("Image: <name>") instead of being loaded.
- **Follow-up questions** ("Ask AI") go to the same local Ollama.

If you point `ollama_url` at another computer, your selected text is sent there. The Settings page warns
you when you save such an address.

## What the web search sends (End only)

End can search the web before explaining. This is the only feature that sends anything derived from your
text to the internet. It runs through SearXNG, a search engine bundled with AI-Hotkeys that runs on your
PC (`127.0.0.1:8888`) and that only your PC can use.

When a search runs:

1. **Search words go to public search engines.** SearXNG forwards the search words to the engines it has
   enabled. The bundled `searxng/settings.yml` enables Startpage and Yahoo and turns off DuckDuckGo, Brave,
   Wikidata and Mojeek; other engines that SearXNG enables by default for general web searches stay on.
   Those engines see the search words and your IP address, as with any web search.
2. **Some of the pages found are downloaded** from their websites: up to `pages_to_read` usable pages
   (default 3), trying at most two extra results when some fail. Those websites see your IP address and a
   normal browser-like request. Nothing about your text is sent to them. Pages on your PC or your local
   network are never contacted (see [SECURITY.md](SECURITY.md)).
3. **Your full text and the answer stay local.** Only the search words leave your PC.

Where the search words come from (`[searxng] query_mode`, "Search words" on the Settings page):

- `allow_fallback` (default): the AI reads your text and writes the search words. If a search is forced
  (the text contains recognized technical terms, or `web_search = always`) and the AI writes no search words,
  the technical terms found in your text, or the **first 10 words of your text**, are searched as they are.
- `model`: only search words written by the AI are sent. Nothing is ever taken verbatim from your text.
  If the AI writes none, there is no search.

When to search (`[searxng] web_search`, "When to search"):

- `auto` (default): the AI first decides whether the text needs a search. Personal notes, opinions and
  messages normally do not.
- `always`: every End searches.
- `false`: never. SearXNG is not even started, and nothing leaves your PC.

The installer's last page and the Settings page show the same notice.

## Temporary files: the `work\` folder

AI-Hotkeys needs to hand your selection from AutoHotkey to Python, so it is briefly written to disk.

- **Each job has its own folder,** `work\runs\<run id>\`, holding the selection (`input.txt`), the result,
  status and error files, and the web sources.
- **The folder is deleted as soon as possible:**
  - by the results page right after it has read the files, before the page is shown. From then on the text
    lives only in the results page's memory, until the page shuts down after about 4 minutes of disuse;
  - by AI-Hotkeys after a direct replace (PgUp), after any error, and after a cancel (Esc);
  - when AI-Hotkeys reloads or exits while a job is running.
- **Leftovers are swept.** Run folders older than 1 hour, left by a crash, are deleted at startup and
  before each job. Files left in `work\` by older versions are deleted at startup.
- **`work\` is private.** At first start AI-Hotkeys restricts it to your account, SYSTEM and
  Administrators.
- **The Obsidian To-Do route** writes the AI's version of the note to `work\obsidian_output.txt`. It is
  deleted after a successful update and kept only when a safety check rejected it, so you can compare.
- **Logs** (`work\server.log`, `work\searxng.log`) record errors and SearXNG's activity. `searxng.log`
  can contain the search words, as any search log does.

The text you copy also passes through the Windows clipboard. After a successful direct replace, the
corrected text stays in the clipboard (as with a normal copy and paste); otherwise your previous
clipboard content is restored. If Windows clipboard history is on, Windows may keep copies.

## Backups of your To-Do note

Before each Obsidian To-Do run, AI-Hotkeys copies the note to the hidden folder `.ai-hotkeys-backups` next to
it, and keeps the newest 20 copies. Obsidian does not index hidden folders, so the copies do not show up in
search. If your vault is synced (OneDrive, Obsidian Sync, Git), the backups may be synced too. Backups made
by older versions (`To-Do List.backup_*.md` next to the note) are never touched; delete them yourself if you
do not need them. Uninstalling never deletes backups.

## Uninstalling

The default uninstall keeps `config.ini` and `work\`; `Uninstall.exe /S /PURGE` deletes them. See
[docs/INSTALL.md](docs/INSTALL.md#5-uninstalling).

## Third parties

- **Ollama** is a separate program with its own privacy terms: <https://ollama.com>.
- **Search engines** used by SearXNG apply their own privacy policies to the search words they receive.
