"""Conjunto de preguntas de evaluacion (etapas 4, 5 y 6).

Cada pregunta lleva la pagina esperada y un texto (`needle`) que debe aparecer en el
fragmento que contiene la respuesta. Un fragmento "acierta" si su titulo es `page`
(o `page` es None) y contiene `needle`. `validate` comprueba contra el corpus real
que cada etiqueta es alcanzable, para no evaluar contra respuestas que no existen.

kind: direct | synonym | no_name | typo | inflection | symbol | no_answer
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Q:
    question: str
    page: str | None
    needle: str | None
    kind: str
    expected: tuple = ()  # el modelo acierta si su respuesta contiene alguna (sin mayusculas)


QUESTIONS = [
    Q("What rarity is Blueprint?", "Blueprint", "Rarity: Rare", "direct", expected=('rare',)),
    Q("How do I unlock Brainstorm?", "Brainstorm",
      "Unlock Requirement: Discard a Royal Flush", "direct", expected=('royal flush',)),
    Q("What does Mime do?", "Mime", "Effect: Retrigger all card held in hand", "direct", expected=('retrigger',)),
    Q("What does The Fool tarot card do?", "The Fool",
      "Effect: Creates the last Tarot or Planet card", "direct", expected=('planet',)),
    Q("What does Cavendish do?", "Cavendish", "Effect: X3 Mult", "direct", expected=('x3',)),
    Q("What is the effect of Fibonacci?", "Fibonacci",
      "Effect: Each played Ace, 2, 3, 5, or 8 gives +8 Mult", "direct", expected=('+8',)),
    Q("What rarity is Chicot?", "Chicot", "Rarity: Legendary", "direct", expected=('legendary',)),
    Q("What does Mercury do?", "Mercury", "Effect: Increases Pair hand value", "direct", expected=('pair',)),
    Q("What does the Overstock voucher do?", "Overstock",
      "Effect: +1 card slot available in shop", "direct", expected=('+1 card slot',)),
    Q("How do I unlock Mr. Bones?", "Mr. Bones", "Unlock Requirement: Lose 5 runs", "direct", expected=('5 runs',)),
    Q("How much does Hologram cost?", "Hologram", "Buy Price: $7", "synonym", expected=('$7',)),
    Q("How much does Mr. Bones cost?", "Mr. Bones", "Buy Price: $5", "synonym", expected=('$5',)),
    Q("How much is Brainstorm worth when sold?", "Brainstorm", "Sell Price: $5", "synonym", expected=('$5',)),
    Q("Which joker copies the ability of the leftmost joker?", "Brainstorm",
      "Copies the ability of leftmost Joker", "no_name", expected=('brainstorm',)),
    Q("Which joker retriggers cards held in hand?", "Mime",
      "Effect: Retrigger all card held in hand", "no_name", expected=('mime',)),
    Q("Which joker gives +15 Mult but can be destroyed at end of round?", "Gros Michel",
      "Effect: +15 Mult, 1 in 6 chance", "symbol", expected=('gros michel',)),
    Q("Which joker gives X3 Mult and has a 1 in 1000 chance of being destroyed?", "Cavendish",
      "Effect: X3 Mult, 1 in 1000 chance", "symbol", expected=('cavendish',)),
    Q("What does Blueprnt do?", "Blueprint",
      "Effect: Copies ability of Joker to the right", "typo", expected=('cop',)),
    Q("How do I unlock Hologrm?", "Hologram",
      "Unlock Requirement: Available from start", "typo", expected=('start',)),
    Q("What rarity is Brainstrom?", "Brainstorm", "Rarity: Rare", "typo", expected=('rare',)),
    Q("What does Fibonaci do?", "Fibonacci", "Effect: Each played Ace", "typo", expected=('+8',)),
    Q("Which jokers retrigger played cards?", None, "Effect: Retrigger", "inflection", expected=('hack', 'dusk', 'hanging chad', 'seltzer', 'sock and buskin')),
    Q("What does the Egg joker do?", "Egg", "Gains $3 of sell value", "direct", expected=('$3',)),
    Q("Does the game have a joker called Pikachu?", None, None, "no_answer"),
    Q("What is the capital of France?", None, None, "no_answer"),
    Q("What is the price of the Superman joker?", None, None, "no_answer"),
]


def is_hit(q, chunk):
    return q.needle is not None and (q.page is None or chunk["title"] == q.page) \
        and q.needle in chunk["text"]


def validate(chunks):
    """Devuelve las preguntas cuya etiqueta no es alcanzable en el corpus."""
    return [q for q in QUESTIONS if q.needle is not None and not any(is_hit(q, c) for c in chunks)]


if __name__ == "__main__":
    from index import Index
    bad = validate(Index.load().chunks)
    print(f"{len(QUESTIONS)} preguntas, {len(bad)} con etiqueta inalcanzable")
    for q in bad:
        print("  SIN RESPALDO:", q)
