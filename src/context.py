"""Etapa 5b: seleccion del contexto que recibira el modelo.

El modelo acepta ~512 tokens (pregunta + contexto) y la recuperacion devuelve mas
fragmentos de los que caben. Estrategia (en este orden, sobre los fragmentos ya
ordenados por puntuacion):

  1. Prioridad por puntuacion: se recorren de mayor a menor. La puntuacion ya premia
     a los fragmentos con varios terminos de la consulta (suma de idf por termino).
  2. Sin redundancia: se descarta un fragmento si su Jaccard de terminos con alguno ya
     elegido es >= REDUNDANCY (traslape de fragmentos vecinos, texto repetido).
  3. Limite de palabras: se corta cuando el siguiente no cabe en MAX_WORDS (si es
     demasiado largo se salta y se prueba con el siguiente, mas corto).
  4. Maximo MAX_CHUNKS fragmentos, para no diluir el contexto.

Complejidad: O(h * c * t) con h fragmentos candidatos, c <= MAX_CHUNKS elegidos y t
terminos por fragmento (conjuntos de terminos + interseccion).
"""
from dataclasses import dataclass, field

from approx import jaccard
from preprocess import terms

MAX_WORDS = 320
MAX_CHUNKS = 4
REDUNDANCY = 0.7
SEPARATOR = "\n\n"


@dataclass
class Context:
    chunks: list = field(default_factory=list)   # Hit elegidos, en orden
    text: str = ""
    spans: list = field(default_factory=list)    # [(inicio, fin, id_fragmento)] en `text`
    skipped: list = field(default_factory=list)  # [(id_fragmento, motivo)]
    words: int = 0

    def chunk_at(self, position):
        """Id del fragmento que contiene la posicion `position` de `text` (o None)."""
        for start, end, cid in self.spans:
            if start <= position < end:
                return cid
        return None


def select_context(hits, max_words=MAX_WORDS, max_chunks=MAX_CHUNKS, redundancy=REDUNDANCY):
    ctx, term_sets = Context(), []
    for hit in hits:
        if len(ctx.chunks) >= max_chunks:
            break
        words = len(hit.text.split())
        if ctx.words + words > max_words:
            ctx.skipped.append((hit.id, "excede el limite de palabras"))
            continue
        tset = set(terms(hit.text))
        if any(jaccard(tset, other) >= redundancy for other in term_sets):
            ctx.skipped.append((hit.id, "redundante"))
            continue
        start = len(ctx.text) + (len(SEPARATOR) if ctx.text else 0)
        ctx.text += (SEPARATOR if ctx.text else "") + hit.text
        ctx.spans.append((start, len(ctx.text), hit.id))
        ctx.chunks.append(hit)
        ctx.words += words
        term_sets.append(tset)
    return ctx
