"""Equivalencias de dominio: vocabulario de la pregunta -> vocabulario de la wiki.

HEURISTICAS escritas a mano, no algoritmos de cadenas. Existen porque ninguna
busqueda por forma de palabra (ni exacta ni aproximada) une "cost" con "Buy Price".

  expansions()       Para la BUSQUEDA: anade terminos extra a la pregunta (peso
                     EXPANSION_WEIGHT < 1); nunca quita los originales. Todos los
                     destinos existen en el corpus (lo verifica tests/test_stage4.py).
  rewrite_question() Para el PROMPT del modelo: reformula plantillas de pregunta con las
                     etiquetas de la ficha de la wiki ("What does X do?" -> "What is the
                     effect of X?"). Se descubrieron observando fallos del modelo en el
                     conjunto de evaluacion, asi que sus resultados son optimistas.
"""
import re

from preprocess import joined

EXPANSION_WEIGHT = 0.7

# Palabras de cortesia/imperativo que no aportan contenido a la BUSQUEDA ("Tell me a rare
# joker"). Solo se ignoran al consultar: el indice y el vocabulario no cambian.
QUERY_STOPWORDS = frozenset({"tell", "please"})

_GROUPS = [
    # (palabras de la pregunta, terminos de la wiki que se anaden)
    ({"cost", "costs", "expensive", "cheap", "cheaper", "pay", "afford", "purchase"},
     ("buy", "price")),
    ({"price"}, ("buy",)),
    ({"worth", "sold", "selling", "resale"}, ("sell", "price")),
    ({"sell"}, ("price",)),
    ({"ability", "abilities", "power", "powers", "function", "works", "work"}, ("effect",)),
    ({"multiplier", "multipliers"}, ("mult",)),
    ({"unlocked", "unlocking", "unlockable", "obtain", "obtained", "acquire"},
     ("unlock", "requirement")),
    ({"unlock"}, ("requirement",)),
    ({"rare", "rarer", "common", "uncommon", "legendary"}, ("rarity",)),
]
EQUIVALENCES = {word: targets for words, targets in _GROUPS for word in words}

# "what does X do?" / "how does X work?" preguntan por el campo Effect de la ficha.
_PATTERNS = [
    (re.compile(r"\bwhat (?:does|do) .+ do\b"), ("effect",)),
    (re.compile(r"\bhow (?:does|do) .+ work\b"), ("effect",)),
]


# Plantillas de pregunta -> etiqueta del campo de la ficha ("Effect:", "Buy Price:", ...).
_REWRITES = [
    (re.compile(r"^what (?:does|do) (?P<x>.+?) do$", re.I), "What is the effect of {x}?"),
    (re.compile(r"^how (?:does|do) (?P<x>.+?) work$", re.I), "What is the effect of {x}?"),
    (re.compile(r"^how much (?:does|do|is) (?P<x>.+?) cost$", re.I),
     "What is the buy price of {x}?"),
    (re.compile(r"^how much (?:is|does|do) (?P<x>.+?) (?:worth when sold|sell for|sell)$", re.I),
     "What is the sell price of {x}?"),
]


# Peticiones que no son una pregunta ("Tell me about X", "Give me a rare joker"): el modelo
# (entrenado con preguntas) se abstiene con esa forma, asi que se convierten en una pregunta.
_REQUEST = re.compile(r"^(?:tell|give|show) me (?P<about>about )?(?P<x>.+)$", re.I)


def rewrite_question(text, is_card=None):
    """Devuelve (pregunta reformulada, True) o (texto original, False).

    is_card: funcion opcional texto -> bool que dice si el texto es el nombre de una carta;
    permite reformular "Tell me about Blueprint" y el nombre suelto ("Blueprint") como
    "What is the effect of Blueprint?".
    """
    core = text.strip().rstrip("?!. ").strip()
    for pattern, template in _REWRITES:
        m = pattern.match(core)
        if m:
            return template.format(x=m.group("x")), True
    m = _REQUEST.match(core)
    if m:
        x = m.group("x")
        if m.group("about") and is_card and is_card(x):
            return f"What is the effect of {x}?", True
        return f"What is {x}?", True
    if is_card and core and is_card(core):
        return f"What is the effect of {core}?", True
    return text, False


def expansions(question, existing_terms):
    """Terminos extra para la pregunta, sin repetir los que ya estan."""
    seen = set(existing_terms)
    extra = []
    q = joined(question)

    def add(targets):
        for t in targets:
            if t not in seen:
                seen.add(t)
                extra.append(t)

    for tok in q.split():
        add(EQUIVALENCES.get(tok, ()))
    for pattern, targets in _PATTERNS:
        if pattern.search(q):
            add(targets)
    return extra
