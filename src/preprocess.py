"""Etapa 2a: preprocesamiento de texto (fragmentos y preguntas usan el mismo).

Tecnicas aplicadas:
  1. Minusculas.
  2. Normalizacion de acentos y simbolos (NFKD, x/palos -> palabras).
  3. Eliminacion de puntuacion y caracteres especiales (conservando $, +, %, x).
  4. Tokenizacion con expresion regular.
  5. Eliminacion de stopwords (vista "terms").
  6. Vocabulario de palabras unicas (se construye en index.py).

Por que no se usa un tokenizador generico: en Balatro "+4 Mult", "X1.5" y "$10"
son informacion clave; borrar la puntuacion los convertiria en "4", "15", "10".
"""
import re
import unicodedata

SYMBOLS = {
    "×": "x", "♠": " spades ", "♥": " hearts ", "♦": " diamonds ", "♣": " clubs ",
    "—": " ", "–": " ", "-": " ",  # guion: "Five-Card" -> "five card"
}
_APOSTROPHE = re.compile(r"['’]s\b|['’]")
# Orden importa: numero con prefijo/sufijo, luego multiplicador xN, luego palabras.
_TOKEN = re.compile(r"[$+]?\d+(?:\.\d+)?%?|x\d+(?:\.\d+)?|[a-z]+")

STOPWORDS = frozenset("""
a an the of to in on at by for from with and or but if as is are was were be been
being am do does did has have had it its this that these those there which what
who whom whose when where why how can could would should will shall may might must
i you he she we they me my your our their them his her than then so such not no
into onto over under about also any each per via up out off
""".split())


def normalize(text):
    """Minusculas, sin acentos, sin simbolos raros ni apostrofes."""
    for symbol, replacement in SYMBOLS.items():
        text = text.replace(symbol, replacement)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _APOSTROPHE.sub("", text.lower())


def tokens(text):
    """Todos los tokens, incluyendo stopwords (para frases y nombres de cartas)."""
    return _TOKEN.findall(normalize(text))


def terms(text):
    """Tokens sin stopwords (para puntuar relevancia)."""
    return [t for t in tokens(text) if t not in STOPWORDS]


def joined(text):
    """Cadena normalizada con tokens separados por un espacio.

    Es el texto sobre el que se corren KMP/Z (etapa 3): una busqueda de
    substring sobre esta cadena es una busqueda de frase sobre tokens.
    """
    return " ".join(tokens(text))
