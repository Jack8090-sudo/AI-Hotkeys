"""Fixed synthetic benchmark corpus (S3).

Deterministic Italian texts in three sizes per action. Written for the
benchmark only: no user documents, no personal data. The sizes are chosen to
stay below qwen_client.max_input_chars() for each action with web_search=false
(rewrite about 9.8k, summarize about 37k, explain about 30.8k characters).
"""

# Paragraphs with deliberate typos and clumsy phrasing (rewrite = PgUp)
_REWRITE = [
    "ciao a tutti, vi scrivo per aggiornarvi sul progetto. la settimana scorsa abbiamo finito la prima "
    "fase dei test e i risultati sono stati abbastanza buoni anche se ci sono ancora dei problemi da "
    "risolvere, sopratutto per quanto riguarda la velocita del caricamento delle pagine.",
    "Il cliente ha chiesto di anticipare la consegna di due settimane, cosa che secondo me non e "
    "possibile senza tagliare qualche funzionalita. ne ho parlato con marco e lui e d'accordo, pero "
    "dobbiamo ancora sentire cosa ne pensa la responsabile del reparto che tornera lunedi.",
    "Per quanto riguarda il budget, abbiamo speso circa il settanta per cento di quello previsto e "
    "mancano ancora tre mesi alla fine. quindi direi che siamo in linea, a patto che non ci siano "
    "spese impreviste come l'anno scorso quando abbiamo dovuto ricomprare due server.",
    "Vi ricordo inoltre che venerdi c'e la riunione mensile alle dieci in sala grande, chi non puo "
    "venire mi avvisi entro giovedi cosi organizzo il collegamento video. portate i vostri appunti e "
    "sopratutto le domande che avete sul nuovo processo di revisione del codice.",
]

# Expository paragraphs (summarize = PgDn)
_SUMMARIZE = [
    "La rete ferroviaria regionale ha registrato nel corso dell'ultimo anno un aumento significativo "
    "dei passeggeri, trainato soprattutto dai pendolari che hanno abbandonato l'auto a causa del "
    "costo del carburante. L'azienda di trasporto ha risposto aumentando le corse nelle ore di punta, "
    "ma i sindacati lamentano che il personale non è stato incrementato in proporzione.",
    "Sul fronte della puntualità i dati sono contrastanti: le linee principali hanno migliorato le "
    "proprie prestazioni grazie ai lavori di ammodernamento della linea, mentre le tratte secondarie "
    "soffrono ancora di ritardi frequenti dovuti a materiale rotabile datato e a guasti agli scambi "
    "che richiedono interventi manuali.",
    "Il piano di investimenti presentato dalla regione prevede l'acquisto di nuovi treni elettrici e "
    "ibridi nei prossimi cinque anni, insieme all'elettrificazione di due linee oggi servite da "
    "convogli diesel. Secondo le stime, l'intervento ridurrebbe le emissioni del trasporto pubblico "
    "regionale di circa un quarto.",
    "Le associazioni dei consumatori chiedono però che una parte delle risorse venga destinata alle "
    "stazioni minori, molte delle quali sono prive di biglietterie, ascensori e sale d'attesa "
    "riscaldate. A loro avviso, senza servizi adeguati nelle stazioni, l'aumento dei passeggeri "
    "rischia di essere temporaneo.",
]

# Technical paragraphs (explain = End)
_EXPLAIN = [
    "Il servizio espone un'API REST dietro un reverse proxy Nginx. Le risposte vengono messe in cache "
    "con un TTL di sessanta secondi, ma le richieste autenticate con token JWT bypassano la cache per "
    "evitare di servire dati di un utente a un altro. Il bilanciamento avviene con l'algoritmo least "
    "connections su tre istanze.",
    "Quando il database PostgreSQL supera l'ottanta per cento delle connessioni disponibili, il pool "
    "applicativo inizia a rifiutare le richieste con HTTP 503. Per mitigare il problema è stato "
    "introdotto PgBouncer in modalità transaction pooling, che però non supporta i prepared statement "
    "lato server usati da alcune librerie ORM.",
    "Il frontend è una single page application che usa il code splitting per caricare i moduli solo "
    "quando servono. Il bundle iniziale pesa circa duecento kilobyte compressi con Brotli; le immagini "
    "vengono servite in formato WebP o AVIF a seconda del supporto del browser tramite l'elemento "
    "picture.",
    "Per il monitoraggio si usano metriche Prometheus con dashboard Grafana e allarmi basati sul "
    "novantacinquesimo percentile della latenza. I log strutturati in JSON vengono raccolti da un "
    "agente e indicizzati, con una retention di trenta giorni per rispettare la policy aziendale.",
]

# Target character counts: small, medium, large
SIZES = {"S": 400, "M": 2000, "L": 6000}

_SOURCES = {"rewrite": _REWRITE, "summarize": _SUMMARIZE, "explain": _EXPLAIN}


def text(action, size):
    """Deterministic text of about SIZES[size] characters for the action."""
    target = SIZES[size]
    paras = _SOURCES[action]
    out, i = [], 0
    while sum(len(p) + 2 for p in out) < target:
        out.append(paras[i % len(paras)])
        i += 1
    joined = "\n\n".join(out)
    if len(joined) > target:
        cut = joined.rfind(". ", 0, target)
        joined = joined[: cut + 1] if cut > target // 2 else joined[:target]
    return joined


def long_text(chars=45000):
    """About `chars` characters of mixed expository text (H11 truncation probe)."""
    paras = _SUMMARIZE + _EXPLAIN
    out, i = [], 0
    while sum(len(p) + 2 for p in out) < chars:
        out.append(f"[{i + 1}] " + paras[i % len(paras)])
        i += 1
    return "\n\n".join(out)[:chars]
