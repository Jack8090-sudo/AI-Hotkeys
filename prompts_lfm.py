"""
AI-Hotkeys — prompts for the built-in model (LFM2.5-230M fine-tuned for AI-Hotkeys).

The model was trained on exactly these short prompts (no rules list, no worked
examples): change them and the answers get worse. prompts.py keeps the longer
prompts written for Ollama models (Gemma); prompt_loader picks the right file
for the engine set in config.ini. Same functions as prompts.py.
"""

NUM_CTX = 16384
OPTIONS = {
    "rewrite": {"temperature": 0.1, "top_p": 0.9, "top_k": 50, "num_predict": 4096},
    "summarize": {"temperature": 0.2, "top_p": 0.9, "top_k": 50, "num_predict": 2048},
    "explain": {"temperature": 0.2, "top_p": 0.9, "top_k": 50, "num_predict": 4096},
    "query": {"temperature": 0.1, "top_p": 0.9, "top_k": 50, "num_predict": 60},
}


def _clean(t):
    return t.replace("\r\n", "\n").strip()


def _chat(system, user):
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ---------------------------------------------------------------- PgUp: fix
REWRITE_SYS = "Sei un correttore di bozze. Rispondi solo con il testo corretto in italiano, senza commenti."
REWRITE_ASK = "Correggi il testo e restituiscilo in italiano corretto:\n\n"

# ---------------------------------------------------------------- PgDn: summary
SUMMARIZE_SYS = "Riassumi testi in italiano. Rispondi solo con il riassunto nel formato dell'esempio."
SUMMARIZE_ASK = "Riassumi questo testo:\n\n"

# ---------------------------------------------------------------- End: explain
EXPLAIN_SYS = ("Spieghi testi in italiano semplice a chi non conosce i termini tecnici. "
               "Usi solo le informazioni del testo e rispetti le negazioni.")
EXPLAIN_ASK = "Spiega questo testo:\n\n"
EXPLAIN_SHORT_SYS = "Spieghi in italiano semplice parole e termini tecnici, in un solo breve paragrafo senza titoli."
EXPLAIN_WEB_SYS = (EXPLAIN_SYS + " Puoi usare le fonti numerate: cita ogni informazione presa da una fonte con il "
                   "suo numero tra parentesi quadre, per esempio [1].")
SHORT_TEXT_WORDS = 6


def first_messages(mode, testo, fonti=None, lunghezza="normale"):
    """The first answer. lunghezza is accepted for compatibility: the model has one length."""
    testo = _clean(testo)
    if mode == "rewrite":
        return _chat(REWRITE_SYS, REWRITE_ASK + testo)
    if mode == "summarize":
        return _chat(SUMMARIZE_SYS, SUMMARIZE_ASK + testo)
    if fonti:
        return _chat(EXPLAIN_WEB_SYS, f"Testo:\n{testo}\n\nFonti:\n{fonti}\n\nSpiega il testo.")
    if len(testo.split()) <= SHORT_TEXT_WORDS:
        return _chat(EXPLAIN_SHORT_SYS, "Spiega in poche righe: " + testo)
    return _chat(EXPLAIN_SYS, EXPLAIN_ASK + testo)


# ---------------------------------------------------------------- End: web queries
QUERY_SYS = ("Decidi se serve una ricerca web per capire il testo. Se il testo nomina cose precise da cercare "
             "(funzioni, API, programmi, errori, sigle) scrivi 1 o 2 query brevi, una per riga. "
             "Se è un pensiero o un messaggio personale rispondi solo NO.")
QUERY_FORCE_SYS = ("Scrivi 1 o 2 query di ricerca web brevi, in inglese, una per riga, sulle cose precise nominate "
                   "nel testo. Di un errore cerca il messaggio, non il nome dello script.")
QUERY_INPUT_CHARS = 6000


def query_messages(testo, force=False):
    testo = _clean(testo)[:QUERY_INPUT_CHARS]
    return _chat(QUERY_FORCE_SYS if force else QUERY_SYS, testo)


# ---------------------------------------------------------------- follow-ups (Ask AI on the results page)
FOLLOWUP_REWRITE_SYS = "Modifichi testi in italiano come chiede l'utente. Rispondi solo con il nuovo testo completo."


def followup_rewrite_messages(originale, attuale, richiesta):
    return _chat(FOLLOWUP_REWRITE_SYS, f"Testo:\n{attuale.strip()}\n\nModifica: {richiesta.strip()}")


FOLLOWUP_QA_SYS = ("Rispondi in italiano alle domande dell'utente sul testo che hai {cosa}. Usa solo le informazioni "
                   "del testo; se la risposta non c'è, dillo. Rispondi in modo diretto, lungo quanto serve.")
FOLLOWUP_QA_WEB = (" Puoi usare anche le fonti numerate: cita ogni informazione presa da una fonte con il suo numero "
                   "tra parentesi quadre, per esempio [1].")
FOLLOWUP_WHAT = {"summarize": "riassunto", "explain": "spiegato"}


def followup_qa_messages(mode, originale, primo_risultato, storia, domanda, fonti=None):
    """Questions about a summary or an explanation (Ask AI on the results page).
    storia = previous (question, answer) pairs; fonti = the web sources block of End, if any."""
    system = FOLLOWUP_QA_SYS.replace("{cosa}", FOLLOWUP_WHAT.get(mode, "elaborato")) + (FOLLOWUP_QA_WEB if fonti else "")
    first = f"Testo:\n{_clean(originale)}" + (f"\n\nFonti:\n{fonti}" if fonti else "")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": first},
                {"role": "assistant", "content": primo_risultato.strip()}]
    for q, a in storia:
        messages += [{"role": "user", "content": q.strip()}, {"role": "assistant", "content": a.strip()}]
    messages.append({"role": "user", "content": domanda.strip()})
    return messages
