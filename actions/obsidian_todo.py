"""
AI-Hotkeys — special mode for Obsidian's "To-Do List.md".

Usage:
    python obsidian_todo.py [file path]   (default: TODO_FILE)

Exit codes:
    0 = file updated
    1 = error (Ollama, file not found, ...)
    2 = safety check failed, original file NOT modified

The outcome is also written to work\\obsidian_status.txt
(first line: OK or ERRORE), so AutoHotkey can show it.
"""

import os
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import qwen_client


# The path is changed in config.ini (todo_file = ...)
TODO_FILE = qwen_client.todo_file()

WORK_DIR = qwen_client.WORK_DIR
OUTPUT_FILE = WORK_DIR / "obsidian_output.txt"
STATUS_FILE = WORK_DIR / "obsidian_status.txt"

LEVELS = ["🟢", "🟡", "🔴"]
CATEGORIES = ["### 🐛 Bug", "### ⚙️ Game Design", "### 💡 Idea"]


# =========================================================
# PROMPT
# =========================================================

PROMPT = """
Devi riorganizzare il file Markdown di una lista di attività Roblox.

La struttura del file è OBBLIGATORIA.

DEVONO ESISTERE ESATTAMENTE QUESTI 3 LIVELLI DI DIFFICOLTÀ:
# 🟢
# 🟡
# 🔴

PER CIASCUNO DEI 3 LIVELLI DEVONO ESISTERE ESATTAMENTE
QUESTE 3 SOTTOCATEGORIE:

### 🐛 Bug
### ⚙️ Game Design
### 💡 Idea

IMPORTANTE:
Il nome deve essere ESATTAMENTE "Idea", NON "Idee".

REGOLE ASSOLUTE:
- NON eliminare attività.
- NON unire due attività in una sola e NON dividere un'attività in più attività.
- NON inventare attività.
- NON inventare informazioni.
- NON cambiare lo stato delle checkbox: [ ] resta [ ] e [x] resta [x].
- NON eliminare link, NON modificare il loro indirizzo o il nome della nota collegata.
- NON eliminare immagini e NON modificare il loro percorso.
- NON eliminare tag (#esempio).
- NON eliminare emoji utili già presenti.
- NON eliminare URL.
- NON eliminare elementi Markdown esistenti.
- Mantieni tutte le informazioni presenti nel file.
- Puoi spostare un'attività nella categoria corretta,
  ma non puoi perderla.
- Mantieni il formato Markdown.
- Mantieni l'organizzazione visiva.
- Mantieni i tre livelli di difficoltà.
- Mantieni le tre sottocategorie sotto OGNI livello.
- Mantieni l'ordine logico delle attività.
- Correggi errori di ortografia e grammatica.
- Rendi le descrizioni più chiare quando necessario.
- Se una parte è scritta in inglese, traducila in italiano.
- Il risultato finale deve essere in italiano.
- Non tradurre nomi propri, nomi tecnici, codice, API,
  funzioni, URL, nomi di note collegate o termini tecnici che non devono essere tradotti.
- Non aggiungere spiegazioni.
- Non aggiungere testo prima o dopo il Markdown.
- Non racchiudere il risultato in un blocco di codice ```.

NON MODIFICARE I TITOLI DELLA STRUTTURA.

La struttura deve essere:

# 🟢

### 🐛 Bug

[attività]

### ⚙️ Game Design

[attività]

### 💡 Idea

[attività]

# 🟡

### 🐛 Bug

[attività]

### ⚙️ Game Design

[attività]

### 💡 Idea

[attività]

# 🔴

### 🐛 Bug

[attività]

### ⚙️ Game Design

[attività]

### 💡 Idea

[attività]

RESTITUISCI SOLO IL CONTENUTO COMPLETO DEL FILE MARKDOWN.

FILE ATTUALE:
{testo}
"""


# =========================================================
# OUTCOME
# =========================================================

class SafetyError(Exception):
    pass


def write_status(ok, lines):
    text = ("OK" if ok else "ERRORE") + "\n" + "\n".join(lines)
    print(text)
    try:
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(text, encoding="utf-8")
    except Exception:
        pass


# =========================================================
# QWEN
# =========================================================

def ask_qwen(testo):
    prompt = PROMPT.replace("{testo}", testo)
    return qwen_client.chat(
        [{"role": "user", "content": prompt}],
        "obsidian_todo",
    )


# =========================================================
# NORMALIZATION
# =========================================================

def normalize(text):
    text = text.replace("\r\n", "\n").strip()

    # Possible model reasoning
    text = re.sub(r"(?s)^<think>.*?</think>\s*", "", text)

    # Result wrapped in ```markdown ... ```
    fence = re.match(r"(?s)^```[a-zA-Z]*\n(.*)\n```$", text)
    if fence:
        text = fence.group(1).strip()

    # Level headings: "## 🟢", "#🟢 " ... -> "# 🟢"
    for level in LEVELS:
        text = re.sub(
            rf"(?m)^#{{1,3}}[ \t]*{level}[ \t]*$",
            f"# {level}",
            text,
        )

    # Category headings (even without the U+FE0F emoji selector)
    text = re.sub(r"(?m)^#{2,4}[ \t]*🐛[ \t]*Bugs?[ \t]*$", "### 🐛 Bug", text)
    text = re.sub(r"(?m)^#{2,4}[ \t]*⚙\ufe0f?[ \t]*Game[ \t]*Design[ \t]*$", "### ⚙️ Game Design", text)
    text = re.sub(r"(?m)^#{2,4}[ \t]*💡[ \t]*Ide[ae][ \t]*$", "### 💡 Idea", text)

    return text + "\n"


# =========================================================
# SAFETY CHECKS
# =========================================================

TASK_RE = re.compile(r"(?m)^[ \t]*(?:[-*+]|\d+[.)])[ \t]+\[(.)\][ \t]")
LIST_RE = re.compile(r"(?m)^[ \t]*(?:[-*+]|\d+[.)])[ \t]+\S")
URL_RE = re.compile(r"https?://[^\s<>()\[\]]+")
WIKILINK_RE = re.compile(r"(!?)\[\[([^\]|#^]+)")
MD_LINK_RE = re.compile(r"(!?)\[[^\]]*\]\(\s*<?([^)\s>]+)")
TAG_RE = re.compile(r"(?<![\w#/&])#([A-Za-zÀ-ÿ0-9_][\w\-/À-ÿ]*)")


def task_states(text):
    return Counter(
        "x" if s in "xX" else s
        for s in TASK_RE.findall(text)
    )


def missing(original_items, new_items):
    """Items present in the original that are missing (or fewer) in the new text."""
    orig = Counter(original_items)
    new = Counter(new_items)
    return sorted(k for k, n in orig.items() if new[k] < n)


def strip_code(text):
    # Inside code blocks "#" are not tags and links do not count.
    text = re.sub(r"(?s)```.*?```", "", text)
    return re.sub(r"`[^`\n]*`", "", text)


def check_structure(text):
    lines = text.split("\n")
    errors = []

    level_pos = {}
    for level in LEVELS:
        found = [i for i, line in enumerate(lines) if line.strip() == f"# {level}"]
        if len(found) != 1:
            errors.append(f"level '# {level}' appears {len(found)} times instead of 1")
        else:
            level_pos[level] = found[0]

    if errors:
        return errors

    order = [level_pos[l] for l in LEVELS]
    if order != sorted(order):
        return ["levels are not in order 🟢 → 🟡 → 🔴"]

    bounds = order + [len(lines)]

    # No category before the first level
    for line in lines[:bounds[0]]:
        if line.strip() in CATEGORIES:
            errors.append(f"category '{line.strip()}' is before level 🟢")

    for i, level in enumerate(LEVELS):
        section = [l.strip() for l in lines[bounds[i] + 1:bounds[i + 1]]]
        found = [l for l in section if l in CATEGORIES]

        if found != CATEGORIES:
            counted = False
            for cat in CATEGORIES:
                n = found.count(cat)
                if n != 1:
                    counted = True
                    errors.append(f"under '# {level}' category '{cat}' appears {n} times instead of 1")
            if not counted:
                errors.append(f"under '# {level}' categories are not in order Bug → Game Design → Idea")

    return errors


def validate(original, new):
    errors = check_structure(new)

    if re.search(r"(?m)^#+[ \t]*💡[ \t]*Idee[ \t]*$", new):
        errors.append("found category 'Idee' instead of 'Idea'")

    # --- tasks and checkboxes ---
    o_tasks, n_tasks = task_states(original), task_states(new)
    if sum(o_tasks.values()) != sum(n_tasks.values()):
        errors.append(
            f"checkbox tasks: {sum(o_tasks.values())} in the original, "
            f"{sum(n_tasks.values())} in the result"
        )
    for state in sorted(set(o_tasks) | set(n_tasks)):
        if o_tasks[state] != n_tasks[state]:
            label = {"x": "done [x]", " ": "to do [ ]"}.get(state, f"with state [{state}]")
            errors.append(f"tasks {label}: {o_tasks[state]} before, {n_tasks[state]} after")

    o_list, n_list = len(LIST_RE.findall(original)), len(LIST_RE.findall(new))
    if n_list < o_list:
        errors.append(f"list items: {o_list} in the original, only {n_list} in the result")

    # --- links, images, URLs, tags ---
    o_clean, n_clean = strip_code(original), strip_code(new)

    lost = missing(URL_RE.findall(o_clean), URL_RE.findall(n_clean))
    if lost:
        errors.append("lost URLs: " + ", ".join(lost[:5]))

    o_wiki = [("image " if e else "") + t.strip() for e, t in WIKILINK_RE.findall(o_clean)]
    n_wiki = [("image " if e else "") + t.strip() for e, t in WIKILINK_RE.findall(n_clean)]
    lost = missing(o_wiki, n_wiki)
    if lost:
        errors.append("lost or changed Obsidian links/images: " + ", ".join(f"[[{x}]]" for x in lost[:5]))

    o_md = [("image " if e else "") + t for e, t in MD_LINK_RE.findall(o_clean)]
    n_md = [("image " if e else "") + t for e, t in MD_LINK_RE.findall(n_clean)]
    lost = missing(o_md, n_md)
    if lost:
        errors.append("lost or changed Markdown links/images: " + ", ".join(lost[:5]))

    lost = missing(TAG_RE.findall(o_clean), TAG_RE.findall(n_clean))
    if lost:
        errors.append("lost tags: " + ", ".join("#" + t for t in lost[:5]))

    # --- truncated answer ---
    if len(original) > 300 and len(new) < len(original) * 0.6:
        errors.append(
            f"result is too short ({len(new)} chars vs {len(original)}): "
            "probably truncated"
        )

    return errors


# =========================================================
# MAIN
# =========================================================

def main():
    todo_file = Path(sys.argv[1]) if len(sys.argv) > 1 else TODO_FILE
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    if not todo_file.exists():
        write_status(False, [f"File not found: {todo_file}"])
        return 1

    raw = todo_file.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    original = raw.decode("utf-8-sig").replace("\r\n", "\n")

    try:
        risposta = ask_qwen(original)
    except Exception as e:
        write_status(False, [f"Ollama error: {e}", "The original file was NOT modified."])
        return 1

    if not risposta.strip():
        write_status(False, ["Qwen returned an empty answer.", "The original file was NOT modified."])
        return 1

    risposta = normalize(risposta)
    OUTPUT_FILE.write_text(risposta, encoding="utf-8")

    errors = validate(original, risposta)
    if errors:
        write_status(False, (
            ["Safety check failed:"]
            + ["• " + e for e in errors[:8]]
            + ["", "The original file was NOT modified.",
               f"Qwen's output is in {OUTPUT_FILE}"]
        ))
        return 2

    # Was the file modified while Qwen was working? Then touch nothing.
    if todo_file.read_bytes() != raw:
        write_status(False, [
            "The file was modified while Qwen was working.",
            "The original file was NOT modified: press PgUp again.",
        ])
        return 2

    # Backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = todo_file.with_name(f"{todo_file.stem}.backup_{timestamp}{todo_file.suffix}")
    shutil.copy2(todo_file, backup_file)

    # Atomic write: first a temp file, then the replacement.
    tmp_file = todo_file.with_name("." + todo_file.name + ".tmp")
    with open(tmp_file, "w", encoding="utf-8", newline=newline) as f:
        f.write(risposta)
    os.replace(tmp_file, todo_file)

    tasks = sum(task_states(original).values())
    write_status(True, [
        "To-Do List updated.",
        f"Tasks checked: {tasks}",
        f"Backup: {backup_file.name}",
    ])
    return 0


if __name__ == "__main__":
    sys.exit(main())
