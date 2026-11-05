import re
import json
from pathlib import Path
from spellchecker import SpellChecker

GLOSSARY_FILE = Path(__file__).parent / "glossary.json"

GRAPHIC_ARTS_DEFAULT_WORDS = {
    "intelliprint", "preflight", "preimpresion", "preimpresión", "cuatricromia", "cuatricromía",
    "cmyk", "rgb", "srgb", "pantone", "pms", "icc", "fogra", "gracol", "swop", "ecicmyk",
    "sangrado", "sangre", "hendido", "troquel", "troquelado", "barniz", "tramado", "lineatura",
    "rip", "maculatura", "estucado", "calado", "sobreimpresion", "sobreimpresión",
    "overprint", "knockout", "mediabox", "trimbox", "bleedbox", "cropbox", "artbox",
    "pikepdf", "pymupdf", "pypdf", "fitz", "pdf", "ppi", "ppp", "dpi", "lpi", "tac",
    "urnieta", "salesianos", "mendizabala", "lhipi", "cpifp", "euskadi", "fp", "anexo",
    "proiektuak", "concertado", "crpc", "crpc3", "crpc6", "crpc5", "ps51", "ps52"
}

def load_custom_glossary():
    words = set(GRAPHIC_ARTS_DEFAULT_WORDS)
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

class PrepressSpellChecker:
    def __init__(self):
        try:
            self.spell = SpellChecker(language='es')
        except Exception:
            self.spell = SpellChecker()
        
        glossary = load_custom_glossary()
        self.spell.word_frequency.load_words(glossary)
        self.corrections_cache = {}

    def check_pdf_text(self, doc_pymupdf, max_suggestions_per_page=6):
        findings = []
        glossary = load_custom_glossary()
        seen_words_page = set()

        for page_num in range(len(doc_pymupdf)):
            page = doc_pymupdf[page_num]
            words_data = page.get_text("words")
            page_text = page.get_text("text")

            page_words = []
            for w in words_data:
                raw_word = w[4]
                clean_word = re.sub(r'^[^\wáéíóúüñÁÉÍÓÚÜÑ]+|[^\wáéíóúüñÁÉÍÓÚÜÑ]+$', '', raw_word)
                if len(clean_word) > 2 and not clean_word.isnumeric():
                    page_words.append((clean_word, w))

            words_to_check = set(cw.lower() for cw, _ in page_words if cw.lower() not in glossary)
            unknown = self.spell.unknown(words_to_check)

            page_suggestions = 0
            for clean_word, w_info in page_words:
                lower = clean_word.lower()
                if lower in unknown and page_suggestions < max_suggestions_per_page:
                    if (page_num, lower) in seen_words_page:
                        continue
                    seen_words_page.add((page_num, lower))

                    # Skip roman numerals
                    if bool(re.match(r'^(M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3}))+$', clean_word, re.IGNORECASE)):
                        continue

                    # Use cache
                    if lower not in self.corrections_cache:
                        self.corrections_cache[lower] = self.spell.correction(clean_word)
                    
                    candidate = self.corrections_cache[lower]
                    if candidate and candidate.lower() != lower:
                        context_snippet = clean_word
                        try:
                            idx = page_text.lower().find(clean_word.lower())
                            if idx != -1:
                                start = max(0, idx - 35)
                                end = min(len(page_text), idx + len(clean_word) + 35)
                                context_snippet = "..." + page_text[start:end].replace('\n', ' ') + "..."
                        except Exception:
                            pass

                        findings.append({
                            "id": f"spell_{page_num+1}_{page_suggestions+1}",
                            "page": page_num + 1,
                            "word": clean_word,
                            "suggestion": candidate,
                            "context": context_snippet,
                            "bbox": [round(w_info[0], 1), round(w_info[1], 1), round(w_info[2], 1), round(w_info[3], 1)],
                            "status": "pending"
                        })
                        page_suggestions += 1

        return findings
