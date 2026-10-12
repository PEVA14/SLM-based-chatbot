"""Etapa GUI (a): autocompletado con Trie para la ventana de preguntas.

Dos fuentes, ambas Trie (src/trie.py):
  * index.names  Trie de nombres de carta  -> sugiere el nombre completo ("mr bo" -> "Mr. Bones"),
                 probando los ultimos 3, 2 y 1 palabras escritas.
  * index.vocab  Trie del vocabulario      -> sugiere la palabra que se esta escribiendo,
                 ordenada por frecuencia en el corpus.

Complejidad por tecla: O(m + S) por consulta al Trie (m = longitud del prefijo,
S = subarbol bajo el prefijo), con a lo sumo 4 consultas.

Es una funcion pura (texto -> sugerencias): no toca la ventana, asi se prueba sin Tk.
"""
import re
from dataclasses import dataclass

from preprocess import joined, normalize

MIN_PREFIX = 2
_WORDS = re.compile(r"\S+")
_LAST_WORD = re.compile(r"[A-Za-z0-9$+.%'’-]+$")


@dataclass(frozen=True)
class Suggestion:
    label: str   # lo que muestra el boton
    insert: str  # texto que reemplaza text[start:]
    start: int   # posicion en el texto donde empieza el reemplazo
    kind: str    # "card" | "word"


def suggest(index, text, k=6, max_cards=3):
    """Hasta k sugerencias para lo que se esta escribiendo al final de `text`."""
    if not text or text[-1].isspace():
        return []
    out, seen = [], set()

    def add(s):
        key = s.insert.lower()
        if key not in seen and len(out) < k:
            seen.add(key)
            out.append(s)

    # 1. nombres de carta: se prueba la cola mas larga primero (3, 2, 1 palabras)
    words = list(_WORDS.finditer(text))
    cards = 0
    for n in (3, 2, 1):
        if len(words) < n or cards >= max_cards:
            continue
        start = words[-n].start()
        prefix = joined(text[start:])
        if len(prefix) < MIN_PREFIX:
            continue
        for name, _ in index.names.complete(prefix, max_cards):
            if name != prefix and cards < max_cards:
                add(Suggestion(index.title_of[name], index.title_of[name], start, "card"))
                cards += 1

    # 2. palabra en curso, por frecuencia en el corpus
    m = _LAST_WORD.search(text)
    if m:
        prefix = normalize(m.group()).strip()
        if len(prefix) >= MIN_PREFIX and " " not in prefix:
            for word in index.autocomplete(prefix, k + 1):
                if word != prefix:
                    shown = word.capitalize() if m.group()[0].isupper() else word
                    add(Suggestion(shown, shown, m.start(), "word"))
    return out


def apply(text, suggestion):
    """Texto resultante de aceptar una sugerencia (con un espacio final)."""
    return text[:suggestion.start] + suggestion.insert + " "
