# S6a — Web search: SSRF guard, deadlines and preflight

User-visible:
- The End key's web search reads result pages only from public internet addresses (http/https,
  ports 80 and 443). Pages on this PC or the local network are never contacted. That covers
  loopback, private/ULA, link-local, CGNAT, multicast, reserved, IPv4-mapped/NAT64/6to4 forms of
  those, and cloud metadata. So are decimal, hex, octal and short IP forms, `localhost` and
  `*.localhost`, and URLs with credentials. Such results still appear as snippets; their page
  text is simply not read. There is deliberately no setting to turn this off.
- Redirects are followed by hand, at most 5, and every hop is checked again.
- A slow page can no longer stall End. Each page has a 12 s wall-clock limit (redirects
  included), and the whole page-reading phase has a 15 s limit. Reading stops as soon as
  `pages_to_read` usable pages have arrived. Among those, pages are still used in search-rank order.
- If Ollama is not running, End no longer starts SearXNG or searches the web first. A 2 s check
  (`/api/tags`) fails fast and the usual Ollama error is shown.
- `[searxng] results` is clamped to 1–10 and `pages_to_read` to 0–5.
- The standard-library fallback (used when curl_cffi is missing or fails) now uses `http.client`
  directly, not `urllib`. It still verifies TLS certificates and still ignores system proxies.

Residual risk:
- DNS rebinding: closed on both paths, because the connection goes to the IP address that was
  checked. curl_cffi uses `CURLOPT_RESOLVE` with proxies disabled (`NOPROXY *`). The stdlib path
  opens the socket to the checked IP and keeps the host name for the Host header and TLS SNI.
- curl_cffi now ignores `HTTP(S)_PROXY` environment variables for page fetches. Before, libcurl
  could honour them. The urllib path never used proxies. A machine that can reach the web only
  through a proxy will read no pages (snippets still work).
- A host that resolves to both public and internal addresses is refused as a whole.
- Pages still downloading when the phase stops are abandoned, not killed. Each one ends by
  itself within its own 12 s limit.
- The SearXNG URL from `config.ini` (normally 127.0.0.1) is trusted and not checked by the guard.

Tests: `tests/test_websearch_ssrf.py` covers the SSRF corpus and the redirect re-checks.
`tests/test_websearch_fetch.py` covers slow-drip deadlines (body and headers), the overall
deadline, early stop, the preflight, the clamps and `web_search=false`. The curl_cffi variants
run only when `searxng/lib` is linked. Positive fetch tests use the test-only seam
`websearch._TEST_LOOPBACK_PORTS`, which is empty in the application.
