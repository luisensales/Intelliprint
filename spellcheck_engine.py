import re
import gzip
import json
from pathlib import Path

GLOSSARY_FILE = Path(__file__).parent / "glossary.json"
WORDLIST_FILE = Path(__file__).parent / "spanish_wordlist.json.gz"

# ─── Glosario técnico de artes gráficas / preimpresión ───────────────────────
GRAPHIC_ARTS_DEFAULT_WORDS = {
    # Preimpresión y producción
    "intelliprint", "preflight", "preimpresion", "preimpresión", "cuatricromia", "cuatricromía",
    "cmyk", "rgb", "srgb", "pantone", "pms", "icc", "fogra", "gracol", "swop", "ecicmyk",
    "sangrado", "sangre", "hendido", "troquel", "troquelado", "barniz", "tramado", "lineatura",
    "rip", "maculatura", "estucado", "calado", "sobreimpresion", "sobreimpresión",
    "overprint", "knockout", "mediabox", "trimbox", "bleedbox", "cropbox", "artbox",
    "pikepdf", "pymupdf", "pypdf", "fitz", "pdf", "ppi", "ppp", "dpi", "lpi", "tac",
    # Términos del centro
    "urnieta", "salesianos", "mendizabala", "lhipi", "cpifp", "euskadi", "fp",
    "proiektuak", "concertado", "crpc", "crpc3", "crpc6", "crpc5", "ps51", "ps52",
    # Tecnicismos digitales / modernos comunes
    "prompt", "prompts", "login", "online", "offline", "streaming", "hashtag",
    "wifi", "bluetooth", "smartphone", "app", "apps", "web", "url", "api",
    "chat", "chatgpt", "inteligencia", "artificial", "digital", "software", "hardware",
    "pixel", "píxel", "pixelado", "render", "rendering", "shader", "bitmap",
    "jpeg", "png", "tiff", "eps", "svg", "gif", "webp", "psd", "ai", "indd",
    # Inglés técnico frecuente en documentos gráficos y TIC
    "open", "source", "free", "page", "code", "debug", "logs", "log", "output",
    "input", "file", "files", "font", "fonts", "layer", "layers", "mask", "clip",
    "print", "printer", "scan", "scanner", "preview", "export", "import", "batch",
    "script", "plugin", "template", "layout", "grid", "bleed", "trim", "crop",
    "color", "colour", "mode", "profile", "intent", "gamut", "depth",
    "factory", "studio", "cloud", "server", "client", "data", "dataset",
    "model", "models", "training", "test", "version", "update", "release",
    "workflow", "pipeline", "canvas", "frame", "frames", "slide", "slides",
    "header", "footer", "caption", "index", "sample", "draft", "proof",
    "basque", "euskera", "euskal", "herria",
    "gemini", "claude", "chatgpt", "midjourney", "stable", "diffusion",
    "pyme", "pymes", "startup", "startups",
    # Abreviaturas y siglas habituales
    "min", "max", "num", "ref", "vol", "pág", "etc", "ej", "uds",
    "www", "http", "https", "ftp", "ssh",
    # Meses y calendarios abreviados
    "ene", "feb", "mar", "abr", "jun", "jul", "ago", "sep", "sept", "oct", "nov", "dic",
}

# ─── Carga del diccionario español principal ──────────────────────────────────
_SPANISH_WORDLIST_CACHE = None

def load_spanish_wordlist():
    global _SPANISH_WORDLIST_CACHE
    if _SPANISH_WORDLIST_CACHE is not None:
        return _SPANISH_WORDLIST_CACHE

    wordset = set()
    if WORDLIST_FILE.exists():
        try:
            with gzip.open(WORDLIST_FILE, 'rt', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                wordset = set(data)
        except Exception:
            pass
    _SPANISH_WORDLIST_CACHE = wordset
    return wordset


def load_custom_glossary():
    words = set(w.lower() for w in GRAPHIC_ARTS_DEFAULT_WORDS)
    if GLOSSARY_FILE.exists():
        try:
            with open(GLOSSARY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    words.update(w.lower() for w in data)
        except Exception:
            pass
    return words


def save_word_to_glossary(word):
    current = load_custom_glossary()
    clean_word = word.strip().lower()
    if clean_word and clean_word not in current:
        current.add(clean_word)
        try:
            with open(GLOSSARY_FILE, "w", encoding="utf-8") as f:
                json.dump(sorted(list(current)), f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False
    return True


# ─── Heurísticas de filtrado ─────────────────────────────────────────────────

ROMAN_RE = re.compile(
    r'^(M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3}))+$',
    re.IGNORECASE
)

def _strip_accents(text):
    """Remove accents so we can compare accent-free versions."""
    return (text
            .replace('á', 'a').replace('é', 'e').replace('í', 'i')
            .replace('ó', 'o').replace('ú', 'u').replace('ü', 'u')
            .replace('Á', 'a').replace('É', 'e').replace('Í', 'i')
            .replace('Ó', 'o').replace('Ú', 'u').replace('Ü', 'u')
            .replace('ñ', 'n').replace('Ñ', 'n'))


def _looks_like_code_or_abbrev(word):
    """
    Returns True for tokens that should never be spell-checked:
      - All-caps abbreviations (PDF, RGB, ICC, URL, …)
      - CamelCase identifiers
      - Mostly digits / mixed codes (A4, PS52, …)
      - Very short words (≤ 2 chars already filtered upstream)
      - Words containing non-Spanish punctuation (dots, slashes, @)
      - English-looking words (mostly consonant clusters uncommon in Spanish)
    """
    # ── Skip codes, abbreviations, CamelCase, all-caps
    if word.isupper():           # PDF, RGB, CMYK, PYMEs
        return True
    if re.search(r'\d', word):   # A4, 300dpi, PS52
        return True
    if re.search(r'[A-Z][a-z]+[A-Z]', word):  # CamelCase
        return True
    # Capitalised proper nouns / English brand names (Gemini, Claude, Basque, Factory…)
    # These are capitalised, mostly non-Spanish, with no known inflection
    if word[0].isupper() and len(word) >= 3:
        return True  # Let the validity check handle capitalised Spanish words separately
    return False


def _is_valid_spanish(word_lower, wordset, glossary):
    """
    Returns True if the word should be considered correctly spelled:
      1. Present in the custom glossary / technical dictionary
      2. Present in the large wordlist (lemmas + verb conjugations)
      3. Present without accents in the wordlist
      4. Deduced plural of a word in the wordlist (word[:-1] or word[:-2]+'a')
      5. Feminine/masculine form of a word in the wordlist
    """
    if word_lower in glossary:
        return True
    if word_lower in wordset:
        return True
    # Accept accent-stripped match
    stripped = _strip_accents(word_lower)
    if stripped in wordset:
        return True

    # ── Plural heuristics ─────────────────────────────────────────
    # Rule 1: word ends in 's' -> try removing 's' (textos -> texto)
    if word_lower.endswith('s') and len(word_lower) > 4:
        singular = word_lower[:-1]
        if singular in wordset or _strip_accents(singular) in wordset:
            return True

    # Rule 2: word ends in 'es' -> try removing 'es' (fallos is covered above;
    #         camiones -> camión won't match, but camion will)
    if word_lower.endswith('es') and len(word_lower) > 5:
        base = word_lower[:-2]
        if base in wordset or _strip_accents(base) in wordset:
            return True

    # Rule 3: words ending in 'iones' -> try base 'ion' (participaciones -> participación)
    if word_lower.endswith('iones') and len(word_lower) > 7:
        base = word_lower[:-5] + 'ión'
        if base in wordset:
            return True
        base2 = word_lower[:-5] + 'ion'
        if base2 in wordset:
            return True

    # Rule 4: feminine -> masculine (obligada -> obligado, otra -> otro, etc.)
    if word_lower.endswith('a') and len(word_lower) >= 4:
        masc = word_lower[:-1] + 'o'
        if masc in wordset:
            return True

    # Rule 5: plural feminine -> singular masculine
    if word_lower.endswith('as') and len(word_lower) >= 4:
        masc = word_lower[:-2] + 'o'
        if masc in wordset:
            return True

    # Rule 6: reflexive / pronoun-cliticised verbs (centrarse, aplicarla, diciéndoles…)
    for suffix in ('rse', 'rme', 'rte', 'rlo', 'rla', 'rlos', 'rlas', 'rle', 'rles',
                   'ndose', 'ndome', 'ndote', 'ndola', 'ndolo', 'ndolos', 'ndolas',
                   'nse', 'ron'):
        if word_lower.endswith(suffix) and len(word_lower) - len(suffix) >= 3:
            base = word_lower[:-len(suffix)]
            # Try base, base+'r', base+'ar', base+'er', base+'ir'
            for candidate in (base, base + 'r', base + 'ar', base + 'er', base + 'ir'):
                if candidate in wordset:
                    return True

    # Rule 7: superlatives in -ísimo/a/os/as — always accept
    if re.search(r'ísim[oa]s?$', word_lower):
        return True

    # Rule 8: z → ces plurals (capaz → capaces, feliz → felices)
    if word_lower.endswith('ces') and len(word_lower) > 5:
        base = word_lower[:-3] + 'z'
        if base in wordset or _strip_accents(base) in wordset:
            return True

    # Rule 9: ón → ones plurals (patrón → patrones, camión → camiones)
    if word_lower.endswith('ones') and len(word_lower) > 6:
        base_accent = word_lower[:-4] + 'ón'
        base_plain  = word_lower[:-4] + 'on'
        if base_accent in wordset or base_plain in wordset:
            return True

    # Rule 10: -ción / -sión endings without the full word (zación fragment, etc.)
    if re.search(r'[cs]ión$', word_lower) or re.search(r'[cs]ion$', word_lower):
        return True

    # Rule 11: -able / -ible adjectives derived from verbs (descargable, imprimible…)
    for suf in ('able', 'ible', 'ables', 'ibles'):
        if word_lower.endswith(suf) and len(word_lower) - len(suf) >= 3:
            base = word_lower[:-len(suf)]
            for candidate in (base, base + 'ar', base + 'er', base + 'ir',
                               base + 'gar', base + 'ger', base + 'car'):
                if candidate in wordset:
                    return True

    # Rule 12: -mente adverbs (rápidamente, fácilmente…)
    if word_lower.endswith('mente') and len(word_lower) > 7:
        base = word_lower[:-5]
        if base in wordset:
            return True
        base_masc = base[:-1] + 'o' if base.endswith('a') else base
        if base_masc in wordset:
            return True

    return False


def _best_suggestion(word_lower, wordset):
    """
    Simple edit-distance-1 candidate search in the wordset.
    Returns None if no good candidate is found.
    """
    # Only suggest if the word is not too short
    if len(word_lower) < 4:
        return None

    candidates = set()

    # Deletion: remove one char at a time
    for i in range(len(word_lower)):
        cand = word_lower[:i] + word_lower[i+1:]
        if cand in wordset and cand != word_lower:
            candidates.add(cand)

    # Replacement: swap each char with common Spanish letters
    alphabet = 'abcdefghijklmnopqrstuvwxyzáéíóúüñ'
    for i in range(len(word_lower)):
        for c in alphabet:
            cand = word_lower[:i] + c + word_lower[i+1:]
            if cand in wordset and cand != word_lower:
                candidates.add(cand)

    # Insertion: add one char at a time
    for i in range(len(word_lower) + 1):
        for c in alphabet:
            cand = word_lower[:i] + c + word_lower[i:]
            if cand in wordset and cand != word_lower:
                candidates.add(cand)

    if not candidates:
        return None

    # Prefer the candidate closest in length and character similarity
    def score(c):
        len_diff = abs(len(c) - len(word_lower))
        # Count chars in common
        common = sum(1 for a, b in zip(word_lower, c) if a == b)
        return (len_diff, -common, len(c))

    return sorted(candidates, key=score)[0]


# ─── Clase principal ──────────────────────────────────────────────────────────

class PrepressSpellChecker:
    def __init__(self):
        self.wordset = load_spanish_wordlist()
        self.glossary = load_custom_glossary()
        self._suggestion_cache = {}

    def _suggest(self, word_lower):
        if word_lower in self._suggestion_cache:
            return self._suggestion_cache[word_lower]
        result = _best_suggestion(word_lower, self.wordset)
        self._suggestion_cache[word_lower] = result
        return result

    def check_pdf_text(self, doc_pymupdf, max_suggestions_per_page=6):
        """
        Analiza el texto del PDF en busca de posibles erratas.
        Sólo reporta palabras que:
          - No estén en el diccionario español (617k formas conjugadas + lemas)
          - No estén en el glosario técnico de taller
          - No sean siglas, códigos, números o abreviaturas
          - Tengan al menos 4 caracteres
          - Para las que exista una sugerencia válida en el diccionario
        """
        findings = []
        seen_globally = set()  # deduplicate the same word across all pages

        for page_num in range(len(doc_pymupdf)):
            page = doc_pymupdf[page_num]
            words_data = page.get_text("words")
            page_text = page.get_text("text")

            page_suggestions = 0

            for w in words_data:
                if page_suggestions >= max_suggestions_per_page:
                    break

                raw_word = w[4]
                # Strip leading/trailing punctuation
                clean_word = re.sub(
                    r'^[^\wáéíóúüñÁÉÍÓÚÜÑ]+|[^\wáéíóúüñÁÉÍÓÚÜÑ]+$', '',
                    raw_word
                )

                # Minimum length (3 visible chars already in original, we require 4)
                if len(clean_word) < 4:
                    continue

                # Skip pure numbers
                if clean_word.isnumeric():
                    continue

                # Skip codes, abbreviations, CamelCase, all-caps
                if _looks_like_code_or_abbrev(clean_word):
                    continue

                # Skip roman numerals
                if ROMAN_RE.match(clean_word):
                    continue

                word_lower = clean_word.lower()

                # Skip already seen globally
                if word_lower in seen_globally:
                    continue

                # Validity check
                if _is_valid_spanish(word_lower, self.wordset, self.glossary):
                    continue

                # Skip words that look like English consonant clusters
                if re.search(r'(ck|wh|th(?!m)|gh|dge|tch)', word_lower):
                    continue

                # Skip word fragments / hyphenation artifacts (end without vowel, short)
                if len(clean_word) <= 5 and word_lower[-1] not in 'aeiouáéíóú':
                    continue

                # Look for a suggestion
                suggestion = self._suggest(word_lower)

                # Reject if no suggestion or suggestion == original
                if not suggestion or suggestion == word_lower:
                    continue

                seen_globally.add(word_lower)

                # Build context snippet
                context_snippet = clean_word
                try:
                    idx = page_text.lower().find(word_lower)
                    if idx != -1:
                        start = max(0, idx - 40)
                        end = min(len(page_text), idx + len(clean_word) + 40)
                        context_snippet = "..." + page_text[start:end].replace('\n', ' ') + "..."
                except Exception:
                    pass

                findings.append({
                    "id": f"spell_{page_num+1}_{page_suggestions+1}",
                    "page": page_num + 1,
                    "word": clean_word,
                    "suggestion": suggestion,
                    "context": context_snippet,
                    "bbox": [round(w[0], 1), round(w[1], 1), round(w[2], 1), round(w[3], 1)],
                    "status": "pending"
                })
                page_suggestions += 1

        return findings
