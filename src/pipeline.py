"""Etapa 5d: flujo completo del chatbot.

    pregunta -> limpieza -> busqueda -> fragmentos -> seleccion de contexto
             -> modelo de lenguaje -> respuesta

mode="approx": busqueda aproximada (etapa 4).
mode="exact" : busqueda exacta con KMP/Z (etapa 3); linea base para la etapa 6.
Prompt = limpieza de typos (query_clean) + reformulacion con etiquetas de la ficha
(lexicon.rewrite_question).
Ambos usan las equivalencias de dominio (lexicon.py), el mismo selector de contexto y el
MISMO prompt (pregunta limpia + reformulada): asi la comparacion mide solo la diferencia
entre recuperar de una forma u otra, no entre dos prompts distintos.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from context import Context, select_context
from index import Index
from lexicon import rewrite_question
from preprocess import joined
from qa_model import Answer, QAModel
from query_clean import CleanQuestion, clean_question
from search_approx import ApproxSearcher
from search_exact import ExactSearcher, SearchResult

MODES = ("approx", "exact")


@dataclass
class Reply:
    question: str
    mode: str
    prompt_question: str          # pregunta que vio el modelo
    clean: CleanQuestion
    search: SearchResult
    context: Context
    answer: Answer
    timings_ms: dict = field(default_factory=dict)
    supporting_chunk: int | None = None
    rewritten: bool = False       # si lexicon.rewrite_question reformulo la pregunta


class ChatBot:
    def __init__(self, k=10, model=None, cache=True):
        """cache=True acelera la busqueda exacta (GUI); las mediciones usan cache=False."""
        self.k = k
        self.index = Index.load()
        self.approx = ApproxSearcher(self.index)
        self._exact = None
        self._cache = cache
        self.model = model or QAModel()

    @property
    def exact(self):
        if self._exact is None:
            self._exact = ExactSearcher(self.index, cache=self._cache)
        return self._exact

    def _is_card(self, text):
        """True si `text` (tal cual lo escribio el usuario) es el nombre de una carta."""
        return self.index.names.get(joined(text)) > 0

    def answer(self, question, mode="approx"):
        if mode not in MODES:
            raise ValueError(f"mode debe ser uno de {MODES}")
        t0 = time.perf_counter()
        clean = clean_question(question, self.approx)
        prompt_q, rewritten = rewrite_question(clean.text, self._is_card)
        t1 = time.perf_counter()

        searcher = self.approx if mode == "approx" else self.exact
        result = searcher.search(question, k=self.k)
        t2 = time.perf_counter()

        ctx = select_context(result.hits)
        t3 = time.perf_counter()

        ans = self.model.answer(prompt_q, ctx.text)
        t4 = time.perf_counter()

        ms = lambda a, b: round((b - a) * 1000, 2)
        return Reply(
            question=question, mode=mode, prompt_question=prompt_q, rewritten=rewritten, clean=clean,
            search=result, context=ctx, answer=ans,
            supporting_chunk=None if ans.abstained else ctx.chunk_at(ans.start),
            timings_ms={"clean": ms(t0, t1), "retrieval": result.timings_ms["total"],
                        "context": ms(t2, t3), "model": ms(t3, t4),
                        "retrieval_total": ms(t1, t3), "total": ms(t0, t4)})


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "What rarity is Blueprint?"
    bot = ChatBot()
    for mode in MODES:
        r = bot.answer(q, mode)
        print(f"[{mode}] {r.answer.text!r} (conf {r.answer.score:.2f}) "
              f"| contexto: {[(c.title, c.id) for c in r.context.chunks]} | {r.timings_ms}")
