# Third-party notices

AI-Hotkeys itself is released under the MIT License (see [`LICENSE`](LICENSE)). The installer and the
release archives also redistribute the third-party software listed below. Each component keeps its own
license. The full license texts are in the [`licenses/`](licenses/) folder, which ships with every
installation next to this file.

> **Not legal advice.** This file was put together carefully from upstream license files and package
> metadata, to help AI-Hotkeys meet its redistribution obligations. It is not legal advice, and it may be
> incomplete or out of date. If you redistribute AI-Hotkeys, or a modified version of it, check the
> obligations yourself and get qualified legal advice where needed.

## Contents

1. [Source code for copyleft components](#1-source-code-for-copyleft-components)
2. [Summary](#2-summary)
3. [AutoHotkey](#3-autohotkey)
4. [SearXNG](#4-searxng)
5. [CPython](#5-cpython)
6. [curl_cffi and libcurl-impersonate](#6-curl_cffi-and-libcurl-impersonate)
7. [Python packages in `searxng/lib`](#7-python-packages-in-searxnglib)
8. [Web assets: marked and fonts](#8-web-assets-marked-and-fonts)
9. [Not redistributed: Ollama and the Qwen model](#9-not-redistributed-ollama-and-the-qwen-model)
10. [Keeping this file current](#10-keeping-this-file-current)

## 1. Source code for copyleft components

Three bundled components come with source-code obligations.

| Component | License | Where the corresponding source is |
|---|---|---|
| AutoHotkey 2.0.19 (`ahk/AutoHotkey64.exe`) | GPL-2.0-only | The AutoHotkey **v2.0.19** source archive is attached to every AI-Hotkeys GitHub Release that ships this binary, next to the installer. Upstream tag: <https://github.com/AutoHotkey/AutoHotkey/tree/v2.0.19>. |
| SearXNG `2026.10.7+6671d89` (`searxng/app/`) | AGPL-3.0-or-later | The SearXNG source tarball for commit [`6671d89`](https://github.com/searxng/searxng/tree/6671d89bede8c9fc108b17bb98916170f5657650) is attached to every AI-Hotkeys GitHub Release, next to the installer. Any changes AI-Hotkeys makes to the SearXNG sources are listed in [§4](#4-searxng). |
| GNU libiconv 1.18, statically linked into lxml 6.1.3's extension modules (`searxng/lib/lxml/*.pyd`) | LGPL-2.1-or-later | lxml 6.1.3 sources: <https://pypi.org/project/lxml/6.1.3/#files>. libiconv 1.18 sources: <https://ftp.gnu.org/pub/gnu/libiconv/libiconv-1.18.tar.gz>. The lxml modules are separate, unmodified files from the official lxml wheel, so you can rebuild them from those sources and replace them. |

Releases attach the archives through the release workflow (plan step S14). If an archive is missing
from a Release, open an issue at <https://github.com/Jack8090-sudo/AI-Hotkeys/issues> and the
maintainer will provide it.

AI-Hotkeys launches SearXNG and AutoHotkey as separate programs. SearXNG listens only on
`127.0.0.1` and serves only the person using that computer.

## 2. Summary

| Component | Version | License | Installed at | Notices in `licenses/` |
|---|---|---|---|---|
| AI-Hotkeys | see `VERSION` | MIT | install folder | `../LICENSE` |
| AutoHotkey | 2.0.19 | GPL-2.0-only; bundled PCRE: BSD-3-Clause | `ahk/` | `autohotkey/` |
| SearXNG | 2026.10.7+6671d89 | AGPL-3.0-or-later; web client libraries: MIT, BSD-2-Clause, Apache-2.0, ISC | `searxng/app/` | `searxng/` |
| CPython (Windows embeddable) | 3.13.x | PSF-2.0, plus the bundled libraries in §5 | `python/` | `cpython/` |
| curl_cffi | 0.16.3 | MIT | `searxng/lib/curl_cffi/` | `python-packages/curl-cffi-0.16.3/` |
| libcurl-impersonate (curl, BoringSSL, nghttp2, ngtcp2, nghttp3, brotli, zstd, zlib) | 2.2.2 | MIT, curl, Apache-2.0, BSD-3-Clause, Zlib | `searxng/lib/curl_cffi.libs/` | `curl-impersonate/` |
| Other Python packages | see §7 | see §7 | `searxng/lib/` | `python-packages/`, `bundled-in-wheels/` |
| marked | 12.0.2 | MIT | `static/marked.min.js` | `marked/` |
| Barlow Semi Condensed, IBM Plex Sans and Mono | — | OFL-1.1 | `static/fonts/` | `fonts/` |
| Ollama, Qwen model | — | not redistributed (§9) | — | — |

## 3. AutoHotkey

- **What:** AutoHotkey 2.0.19 (`ahk/AutoHotkey64.exe`), from the official release
  <https://github.com/AutoHotkey/AutoHotkey/releases/tag/v2.0.19>. It runs `main.ahk` and is not modified.
- **License:** GNU General Public License version 2. Text: [`licenses/autohotkey/license.txt`](licenses/autohotkey/license.txt),
  identical to `ahk/license.txt` and to upstream `license.txt` at `v2.0.19`.
- **Bundled:** the PCRE regular-expression library (release 8), under the BSD licence in
  [`licenses/autohotkey/pcre-LICENCE.txt`](licenses/autohotkey/pcre-LICENCE.txt) (upstream
  `source/lib_pcre/pcre/LICENCE` at `v2.0.19`).
- **Source:** see [§1](#1-source-code-for-copyleft-components).

## 4. SearXNG

- **What:** SearXNG `2026.10.7+6671d89` (`searxng/app/searx/`), the local metasearch engine behind web search.
  Upstream: <https://github.com/searxng/searxng>, commit `6671d89bede8c9fc108b17bb98916170f5657650`.
- **License:** GNU Affero General Public License v3.0 or later. Text: [`licenses/searxng/LICENSE.txt`](licenses/searxng/LICENSE.txt),
  identical to upstream `LICENSE` at that commit and to `searxng/LICENSE-searxng.txt`.
- **Modifications:** AI-Hotkeys vendors SearXNG's `searx/` package as published at that commit. Whether it
  differs from upstream is checked by plan step S11 (hypothesis H17). If that check finds a difference, the
  patch is published here and attached to the Release with the source tarball. AI-Hotkeys' own files around
  SearXNG (`searxng/avvia_searxng.py`, the launcher, and `searxng/settings.yml`, its configuration) are MIT
  and are not part of SearXNG.
- **Web client libraries.** The minified scripts and styles in `searx/static/themes/simple/` include these
  npm packages (versions from SearXNG's `client/simple/package-lock.json` at the pinned commit; the
  scripts were identified from the shipped source maps):

  | Package | Version | License | Notice |
  |---|---|---|---|
  | ol (OpenLayers) | 10.10.0 | BSD-2-Clause | `licenses/searxng/frontend/openlayers-10.10.0-LICENSE.md` |
  | mathjs | 15.2.0 | Apache-2.0 | `mathjs-15.2.0-LICENSE.txt`, `mathjs-15.2.0-NOTICE.txt` |
  | @babel/runtime | 7.29.7 | MIT | `babel-runtime-7.29.7-LICENSE.txt` |
  | typed-function | 4.2.2 | MIT | `typed-function-4.2.2-LICENSE.txt` |
  | escape-latex | 1.2.0 | MIT | `escape-latex-1.2.0-LICENSE.md` |
  | tiny-emitter | 2.1.0 | MIT | `tiny-emitter-2.1.0-LICENSE.txt` |
  | quickselect | 3.0.0 | ISC | `quickselect-3.0.0-LICENSE.txt` |
  | rbush | 4.0.1 | MIT | `rbush-4.0.1-LICENSE.txt` |
  | swiped-events | 1.2.0 | MIT | `swiped-events-1.2.0-LICENSE.txt` |
  | ionicons (icons) | 8.1.0 | MIT | `ionicons-8.1.0-LICENSE.txt` |
  | normalize.css | 8.0.1 | MIT | `normalize.css-8.0.1-LICENSE.md` |

- **Data:** `searx/data/` holds datasets that SearXNG builds from public sources (for example Wikidata).
  They are distributed as part of SearXNG; their provenance is documented in the SearXNG source.
- **Source:** see [§1](#1-source-code-for-copyleft-components).

## 5. CPython

- **What:** the official CPython 3.13 Windows x64 build (`python/`), from <https://www.python.org/downloads/windows/>.
  The release build uses the embeddable package (plan decision D2). The exact 3.13.x version is pinned in
  `build/pins.json`.
- **License:** Python Software Foundation License Version 2, plus the older BeOpen, CNRI and CWI licenses
  for historical code. Text: [`licenses/cpython/LICENSE-windows-build.txt`](licenses/cpython/LICENSE-windows-build.txt)
  (the `LICENSE.txt` of the Windows build, which also ships as `python/LICENSE.txt`). It also covers
  bzip2 and the Microsoft Visual C++ runtime (`vcruntime140*.dll`), which the Windows build includes under
  Microsoft's redistribution terms.
- **Incorporated software.** [`licenses/cpython/license.rst`](licenses/cpython/license.rst) is CPython's own
  "Licenses and Acknowledgements for Incorporated Software" (`Doc/license.rst` at `v3.13.7`). It covers,
  among others, expat, libffi, zlib, libmpdec, OpenSSL, HACL\*, mimalloc, SipHash and the Mersenne Twister.
  The libraries shipped as separate files or linked in are:

  | Library | Version (3.13.7 / 3.13.16) | License | Notice |
  |---|---|---|---|
  | OpenSSL (`libcrypto-3-x64.dll`, `libssl-3-x64.dll`) | 3.0.16 / 3.5.9 | Apache-2.0 | `cpython/openssl-LICENSE.txt` (same text for both versions) |
  | libffi (`libffi-8.dll`) | 3.4.4 | MIT | `cpython/libffi-LICENSE.txt` |
  | SQLite (`sqlite3.dll`) | as shipped by python.org | public domain | none required (<https://sqlite.org/copyright.html>) |
  | liblzma from XZ Utils (`_lzma.pyd`) | 5.2.5 | public domain | `cpython/xz-COPYING.txt` |
  | expat (`pyexpat.pyd`) | 2.7.x | MIT | `cpython/expat-COPYING.txt` |
  | zlib (in `python313.dll`) | 1.3.1 | Zlib | `cpython/license.rst` |
  | libmpdec (`_decimal.pyd`) | 4.0.0 | BSD-2-Clause | `cpython/license.rst` |
  | bzip2 (`_bz2.pyd`) | 1.0.8 | bzip2-1.0.6 | `cpython/LICENSE-windows-build.txt` |

  Versions come from CPython's `PCbuild/get_externals.bat` at each tag and from the binaries themselves.
  Tcl/Tk is not shipped (the embeddable package has no tkinter).

## 6. curl_cffi and libcurl-impersonate

`curl_cffi` 0.16.3 (MIT) is the HTTP client SearXNG uses. Its Windows wheel includes
`curl_cffi.libs/libcurl-impersonate-*.dll`, which is **libcurl-impersonate 2.2.2**
(<https://github.com/lexiforest/curl-impersonate/tree/v2.2.2>). That DLL statically links the libraries
below, at the versions pinned in curl-impersonate's `CMakeLists.txt` at `v2.2.2`. The curl and zlib versions
were confirmed from strings in the shipped DLL.

| Library | Version | License | Notice in `licenses/curl-impersonate/` |
|---|---|---|---|
| curl-impersonate (patches and build) | 2.2.2 | MIT | `curl-impersonate-LICENSE.txt` |
| curl / libcurl | 8.21.0 | curl (MIT-style) | `curl-COPYING.txt` |
| BoringSSL | commit `156c7b75ae9b8c3b3f847acf264f17594c3859fb` | Apache-2.0 (the Go-licensed test code named in the file is not compiled in) | `boringssl-LICENSE.txt` |
| nghttp2 | 1.63.0 | MIT | `nghttp2-COPYING.txt` |
| ngtcp2 | 1.20.0 | MIT | `ngtcp2-COPYING.txt` |
| nghttp3 | 1.15.0 | MIT | `nghttp3-COPYING.txt` |
| brotli | 1.2.0 | MIT | `brotli-LICENSE.txt` |
| zstd | 1.5.7 | BSD-3-Clause (zstd is dual-licensed BSD/GPL-2.0; it is used here under BSD) | `zstd-LICENSE.txt` |
| zlib | 1.3.1 | Zlib | `zlib-LICENSE.txt` |

Every text was taken from the upstream repository at the tag or commit listed.

## 7. Python packages in `searxng/lib`

These are SearXNG's runtime dependencies, installed from the official PyPI wheels and not modified. Each
package's license files are copied to `licenses/python-packages/<name>-<version>/`. That includes license
files that ship inside a package, for example Babel's Unicode CLDR data license, the click copy vendored
in typer, and the Silk icon credit (CC-BY-2.5, by Mark James) in Werkzeug's debugger. Three wheels
statically link native libraries, whose notices are in [`licenses/bundled-in-wheels/`](licenses/bundled-in-wheels/):
lxml (libxml2, libxslt, zlib, libiconv; see §1 for libiconv's LGPL), PyYAML (libyaml) and cffi (libffi).

certifi is under MPL-2.0. Its unmodified source is at <https://github.com/certifi/python-certifi> and
<https://pypi.org/project/certifi/#files>.

The table below is generated by `tools/licenses/gen_notices.py` from the packages' `*.dist-info` metadata.
Do not edit it by hand.

<!-- BEGIN GENERATED: python-packages (tools/licenses/gen_notices.py) -->

| Package | Version | License (SPDX) | Notices in `licenses/python-packages/` |
|---|---|---|---|
| [annotated-doc](https://github.com/fastapi/annotated-doc) | 0.0.5 | MIT | `annotated-doc-0.0.5/` |
| [babel](https://github.com/python-babel/babel) | 2.18.0 | BSD-3-Clause | `babel-2.18.0/` |
| [blinker](https://github.com/pallets-eco/blinker/) | 1.9.0 | MIT | `blinker-1.9.0/` |
| [certifi](https://github.com/certifi/python-certifi) | 2026.7.22 | MPL-2.0 | `certifi-2026.7.22/` |
| [cffi](https://github.com/python-cffi/cffi) | 2.1.1 | MIT-0 | `cffi-2.1.1/`; statically bundles libffi (MIT), from cffi's src/c/libffi_x86_x64 |
| [click](https://github.com/pallets/click/) | 8.5.0 | BSD-3-Clause | `click-8.5.0/` |
| [colorama](https://github.com/tartley/colorama) | 0.4.6 | BSD-3-Clause | `colorama-0.4.6/` |
| [curl-cffi](https://github.com/lexiforest/curl_cffi) | 0.16.3 | MIT | `curl-cffi-0.16.3/` |
| [flask](https://github.com/pallets/flask/) | 3.1.3 | BSD-3-Clause | `flask-3.1.3/` |
| [flask-babel](https://github.com/python-babel/flask-babel) | 4.0.0 | BSD-3-Clause | `flask-babel-4.0.0/` |
| [isodate](https://github.com/gweis/isodate/) | 0.7.2 | BSD-3-Clause | `isodate-0.7.2/` |
| [itsdangerous](https://github.com/pallets/itsdangerous/) | 2.2.0 | BSD-3-Clause | `itsdangerous-2.2.0/` |
| [jinja2](https://github.com/pallets/jinja/) | 3.1.6 | BSD-3-Clause | `jinja2-3.1.6/` |
| [lxml](https://github.com/lxml/lxml) | 6.1.3 | BSD-3-Clause | `lxml-6.1.3/`; statically bundles libxml2 2.14.6 (MIT), libxslt/libexslt 1.1.43 (MIT), zlib 1.3.2 (Zlib), libiconv 1.18 (LGPL-2.1-or-later) |
| [markdown-it-py](https://github.com/executablebooks/markdown-it-py) | 4.2.0 | MIT | `markdown-it-py-4.2.0/` |
| [markupsafe](https://github.com/pallets/markupsafe/) | 3.0.4 | BSD-3-Clause | `markupsafe-3.0.4/` |
| [mdurl](https://github.com/executablebooks/mdurl) | 0.1.2 | MIT | `mdurl-0.1.2/` |
| [msgspec](https://github.com/msgspec/msgspec) | 0.22.0 | BSD-3-Clause | `msgspec-0.22.0/` |
| [pycparser](https://github.com/eliben/pycparser) | 3.1 | BSD-3-Clause | `pycparser-3.1/` |
| [pygments](https://github.com/pygments/pygments) | 2.21.0 | BSD-2-Clause | `pygments-2.21.0/` |
| [python-dateutil](https://github.com/dateutil/dateutil) | 2.9.0.post0 | Apache-2.0 AND BSD-3-Clause | `python-dateutil-2.9.0.post0/` |
| [pytz](https://github.com/stub42/pytz.git) | 2026.5 | MIT | `pytz-2026.5/` |
| [pyyaml](https://github.com/yaml/pyyaml) | 6.0.3 | MIT | `pyyaml-6.0.3/`; statically bundles libyaml 0.2.5 (MIT) |
| [rich](https://github.com/Textualize/rich) | 15.0.0 | MIT | `rich-15.0.0/` |
| [shellingham](https://github.com/sarugaku/shellingham) | 1.5.4 | ISC | `shellingham-1.5.4/` |
| [six](https://github.com/benjaminp/six) | 1.17.0 | MIT | `six-1.17.0/` |
| [typer](https://github.com/fastapi/typer) | 0.27.2 | MIT | `typer-0.27.2/` |
| [typing-extensions](https://github.com/python/typing_extensions) | 4.16.0 | PSF-2.0 | `typing-extensions-4.16.0/` |
| [tzdata](https://github.com/python/tzdata) | 2026.5 | Apache-2.0 | `tzdata-2026.5/` |
| [valkey](https://github.com/valkey-io/valkey-py) | 6.1.1 | MIT | `valkey-6.1.1/` |
| [werkzeug](https://github.com/pallets/werkzeug/) | 3.1.9 | BSD-3-Clause | `werkzeug-3.1.9/` |
| [whitenoise](https://github.com/evansd/whitenoise) | 6.12.0 | MIT | `whitenoise-6.12.0/` |

<!-- END GENERATED: python-packages -->

## 8. Web assets: marked and fonts

- **marked 12.0.2** (`static/marked.min.js`), the Markdown renderer of the result viewer. MIT,
  Copyright (c) 2018+ MarkedJS and (c) 2011-2018 Christopher Jeffrey. Text: [`licenses/marked/LICENSE.md`](licenses/marked/LICENSE.md)
  (upstream `LICENSE.md` at `v12.0.2`).
- **Barlow Semi Condensed** (500, 600), Copyright 2017 The Barlow Project Authors
  (<https://github.com/jpt/barlow>), SIL Open Font License 1.1. Text: [`licenses/fonts/OFL-Barlow.txt`](licenses/fonts/OFL-Barlow.txt).
- **IBM Plex Sans and IBM Plex Mono**, Copyright 2019 IBM Corp., SIL Open Font License 1.1.
  Text: [`licenses/fonts/OFL-IBM-Plex.txt`](licenses/fonts/OFL-IBM-Plex.txt).
- The fonts are unmodified Latin subsets in WOFF2 format. The same OFL texts also ship next to them in `static/fonts/`.

## 9. Not redistributed: Ollama and the Qwen model

AI-Hotkeys does not include Ollama or any language model. You install them yourself, and their own terms apply.

- **Ollama:** MIT License, <https://github.com/ollama/ollama/blob/main/LICENSE>. Download: <https://ollama.com/download>.
- **Qwen model:** the default model is `qwen3.5:9b`, which you download with `ollama pull qwen3.5:9b`.
  Qwen3.5-9B is released by the Qwen team under the Apache License 2.0; see the official model card at
  <https://huggingface.co/Qwen/Qwen3.5-9B>. If you configure a different model, that model's license applies.
- **Search engines:** with web search on, your local SearXNG sends queries to the public search engines
  set in `searxng/settings.yml`. Their terms of service apply to that use.

## 10. Keeping this file current

- `python tools/licenses/gen_notices.py --lib <path to searxng/lib>` regenerates §7 and
  `licenses/python-packages/`. With `--check`, it fails if they are stale.
- `python tools/licenses/check_notices.py build/out/manifest.txt` fails the build if any file in the release
  payload is not covered by a notice in this file, or if a covered package or bundled binary changed version
  without its notices being re-verified. The registry it uses is `tools/licenses/components.json`.
- When AutoHotkey, SearXNG, CPython, curl_cffi, lxml, PyYAML or cffi is upgraded, refresh the matching
  texts in `licenses/` from upstream at the new version, then update `components.json` and this file.
