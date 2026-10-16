"""
AI-Hotkeys — Modalità speciale per "To-Do List.md" di Obsidian.

Uso:
    python obsidian_todo.py [percorso del file]   (default: TODO_FILE)

Codici di uscita:
    0 = file aggiornato
    1 = errore (Ollama, file non trovato, ...)
    2 = controllo di sicurezza fallito, file originale NON modificato

L'esito viene scritto anche in work\\obsidian_status.txt
(prima riga: OK oppure ERRORE), così AutoHotkey può mostrarlo.
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


# Il percorso si cambia in config.ini (todo_file = ...)
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
# ESITO
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
# NORMALIZZAZIONE
# =========================================================

def normalize(text):
    text = text.replace("\r\n", "\n").strip()

    # Eventuale ragionamento del modello
    text = re.sub(r"(?s)^<think>.*?</think>\s*", "", text)

    # Risultato racchiuso in ```markdown ... ```
    fence = re.match(r"(?s)^```[a-zA-Z]*\n(.*)\n```$", text)
    if fence:
        text = fence.group(1).strip()

    # Titoli dei livelli: "## 🟢", "#🟢 " ... -> "# 🟢"
    for level in LEVELS:
        text = re.sub(
            rf"(?m)^#{{1,3}}[ \t]*{level}[ \t]*$",
            f"# {level}",
            text,
        )

    # Titoli delle categorie (anche senza il selettore emoji U+FE0F)
    text = re.sub(r"(?m)^#{2,4}[ \t]*🐛[ \t]*Bugs?[ \t]*$", "### 🐛 Bug", text)
    text = re.sub(r"(?m)^#{2,4}[ \t]*⚙\ufe0f?[ \t]*Game[ \t]*Design[ \t]*$", "### ⚙️ Game Design", text)
    text = re.sub(r"(?m)^#{2,4}[ \t]*💡[ \t]*Ide[ae][ \t]*$", "### 💡 Idea", text)

    return text + "\n"


# =========================================================
# CONTROLLI DI SICUREZZA
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
    """Elementi presenti nell'originale che mancano (o sono meno) nel nuovo."""
    orig = Counter(original_items)
    new = Counter(new_items)
    return sorted(k for k, n in orig.items() if new[k] < n)


def strip_code(text):
    # Nei blocchi di codice "#" non sono tag e i link non contano.
    text = re.sub(r"(?s)```.*?```", "", text)
    return re.sub(r"`[^`\n]*`", "", text)


def check_structure(text):
    lines = text.split("\n")
    errors = []

    level_pos = {}
    for level in LEVELS:
        found = [i for i, line in enumerate(lines) if line.strip() == f"# {level}"]
        if len(found) != 1:
            errors.append(f"il livello '# {level}' compare {len(found)} volte invece di 1")
        else:
            level_pos[level] = found[0]

    if errors:
        return errors

    order = [level_pos[l] for l in LEVELS]
    if order != sorted(order):
        return ["i livelli non sono nell'ordine 🟢 → 🟡 → 🔴"]

    bounds = order + [len(lines)]

    # Nessuna categoria prima del primo livello
    for line in lines[:bounds[0]]:
        if line.strip() in CATEGORIES:
            errors.append(f"la categoria '{line.strip()}' si trova prima del livello 🟢")

    for i, level in enumerate(LEVELS):
        section = [l.strip() for l in lines[bounds[i] + 1:bounds[i + 1]]]
        found = [l for l in section if l in CATEGORIES]

        if found != CATEGORIES:
            counted = False
            for cat in CATEGORIES:
                n = found.count(cat)
                if n != 1:
                    counted = True
                    errors.append(f"sotto '# {level}' la categoria '{cat}' compare {n} volte invece di 1")
            if not counted:
                errors.append(f"sotto '# {level}' le categorie non sono nell'ordine Bug → Game Design → Idea")

    return errors


def validate(original, new):
    errors = check_structure(new)

    if re.search(r"(?m)^#+[ \t]*💡[ \t]*Idee[ \t]*$", new):
        errors.append("trovata la categoria 'Idee' invece di 'Idea'")

    # --- attività e checkbox ---
    o_tasks, n_tasks = task_states(original), task_states(new)
    if sum(o_tasks.values()) != sum(n_tasks.values()):
        errors.append(
            f"attività con checkbox: {sum(o_tasks.values())} nell'originale, "
            f"{sum(n_tasks.values())} nel risultato"
        )
    for state in sorted(set(o_tasks) | set(n_tasks)):
        if o_tasks[state] != n_tasks[state]:
            label = {"x": "completate [x]", " ": "da fare [ ]"}.get(state, f"con stato [{state}]")
            errors.append(f"attività {label}: {o_tasks[state]} prima, {n_tasks[state]} dopo")

    o_list, n_list = len(LIST_RE.findall(original)), len(LIST_RE.findall(new))
    if n_list < o_list:
        errors.append(f"elementi di elenco: {o_list} nell'originale, solo {n_list} nel risultato")

    # --- link, immagini, URL, tag ---
    o_clean, n_clean = strip_code(original), strip_code(new)

    lost = missing(URL_RE.findall(o_clean), URL_RE.findall(n_clean))
    if lost:
        errors.append("URL persi: " + ", ".join(lost[:5]))

    o_wiki = [("immagine " if e else "") + t.strip() for e, t in WIKILINK_RE.findall(o_clean)]
    n_wiki = [("immagine " if e else "") + t.strip() for e, t in WIKILINK_RE.findall(n_clean)]
    lost = missing(o_wiki, n_wiki)
    if lost:
        errors.append("link/immagini Obsidian persi o modificati: " + ", ".join(f"[[{x}]]" for x in lost[:5]))

    o_md = [("immagine " if e else "") + t for e, t in MD_LINK_RE.findall(o_clean)]
    n_md = [("immagine " if e else "") + t for e, t in MD_LINK_RE.findall(n_clean)]
    lost = missing(o_md, n_md)
    if lost:
        errors.append("link/immagini Markdown persi o modificati: " + ", ".join(lost[:5]))

    lost = missing(TAG_RE.findall(o_clean), TAG_RE.findall(n_clean))
    if lost:
        errors.append("tag persi: " + ", ".join("#" + t for t in lost[:5]))

    # --- risposta troncata ---
    if len(original) > 300 and len(new) < len(original) * 0.6:
        errors.append(
            f"il risultato è troppo corto ({len(new)} caratteri contro {len(original)}): "
            "probabilmente è stato troncato"
        )

    return errors


# =========================================================
# MAIN
# =========================================================

def main():
    todo_file = Path(sys.argv[1]) if len(sys.argv) > 1 else TODO_FILE
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    if not todo_file.exists():
        write_status(False, [f"File non trovato: {todo_file}"])
        return 1

    raw = todo_file.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    original = raw.decode("utf-8-sig").replace("\r\n", "\n")

    try:
        risposta = ask_qwen(original)
    except Exception as e:
        write_status(False, [f"Errore Ollama: {e}", "Il file originale NON è stato modificato."])
        return 1

    if not risposta.strip():
        write_status(False, ["Gemma ha restituito una risposta vuota.", "Il file originale NON è stato modificato."])
        return 1

    risposta = normalize(risposta)
    OUTPUT_FILE.write_text(risposta, encoding="utf-8")

    errors = validate(original, risposta)
    if errors:
        write_status(False, (
            ["Controllo di sicurezza fallito:"]
            + ["• " + e for e in errors[:8]]
            + ["", "Il file originale NON è stato modificato.",
               f"Il risultato di Gemma è in {OUTPUT_FILE}"]
        ))
        return 2

    # Il file è stato modificato mentre Gemma lavorava? Allora non tocchiamo nulla.
    if todo_file.read_bytes() != raw:
        write_status(False, [
            "Il file è stato modificato mentre Gemma lavorava.",
            "Il file originale NON è stato modificato: premi di nuovo PgUp.",
        ])
        return 2

    # Backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = todo_file.with_name(f"{todo_file.stem}.backup_{timestamp}{todo_file.suffix}")
    shutil.copy2(todo_file, backup_file)

    # Scrittura atomica: prima un file temporaneo, poi la sostituzione.
    tmp_file = todo_file.with_name("." + todo_file.name + ".tmp")
    with open(tmp_file, "w", encoding="utf-8", newline=newline) as f:
        f.write(risposta)
    os.replace(tmp_file, todo_file)

    tasks = sum(task_states(original).values())
    write_status(True, [
        "To-Do List aggiornata.",
        f"Attività controllate: {tasks}",
        f"Backup: {backup_file.name}",
    ])
    return 0


if __name__ == "__main__":
    sys.exit(main())
