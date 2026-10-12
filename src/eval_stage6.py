"""Datos nuevos para la etapa 6: escalado con el tamano de la coleccion y efecto de la
seleccion de contexto en el modelo. (La comparacion exacta vs aproximada ya esta medida
en eval_stage4.py [recuperacion] y eval_stage5.py [modelo]; figures.py las junta.)

Experimento A -- escalado. Se construye el indice sobre 0.25x, 0.5x, 1x, 2x y 4x del
  corpus (para >1x se REPITEN los fragmentos con ids nuevos: es sintetico, sirve para el
  tiempo, no para la calidad) y se mide la recuperacion de 8 preguntas representativas
  con tres buscadores: exact_kmp (barrido), exact_index (tabla hash) y approx.
Experimento B -- contexto. Con la recuperacion aproximada fija, se varia como se arma el
  contexto (cuantos fragmentos, filtro de redundancia, presupuesto de palabras) y se
  anade ruido (fragmentos al azar de otras paginas); se mide la respuesta del modelo.

Salida: data/stage6_results.json     Uso: python src/eval_stage6.py
"""
import json
import random
import statistics
import time

from context import select_context
from eval_questions import QUESTIONS, is_hit
from index import CHUNKS_PATH, Index
from lexicon import rewrite_question
from pipeline import ChatBot
from query_clean import clean_question
from search_approx import ApproxSearcher
from search_exact import ExactSearcher, Hit

OUT = CHUNKS_PATH.parent / "stage6_results.json"
SCALE_FACTORS = (0.25, 0.5, 1, 2, 4)
SCALE_QUESTIONS = [0, 2, 10, 13, 15, 17, 21, 23]  # un caso de cada tipo
APPROX_RUNS = 3
SEED = 20261002


# --------------------------------------------------------------------------- A
def scaled_chunks(chunks, factor):
    if factor <= 1:
        sub = chunks[: int(len(chunks) * factor)]
    else:
        sub = [c for _ in range(int(factor)) for c in chunks]
    return [{**c, "id": i} for i, c in enumerate(sub)]


def mean_retrieval_ms(searcher, questions, runs):
    per_question = []
    for q in questions:
        times = [searcher.search(q.question, k=10).timings_ms["total"] for _ in range(runs)]
        per_question.append(statistics.median(times))
    return round(statistics.mean(per_question), 2)


def experiment_scaling(chunks):
    questions = [QUESTIONS[i] for i in SCALE_QUESTIONS]
    rows = []
    for factor in SCALE_FACTORS:
        sub = scaled_chunks(chunks, factor)
        t0 = time.perf_counter()
        idx = Index(sub)
        build_ms = round((time.perf_counter() - t0) * 1000)
        exact = ExactSearcher(idx, expand=True, cache=False)
        row = {"factor": factor, "chunks": len(sub), "corpus_chars": len(exact.corpus),
               "index_build_ms": build_ms,
               "exact_kmp_ms": mean_retrieval_ms(exact, questions, 1),
               "exact_index_ms": mean_retrieval_ms(
                   ApproxSearcher(idx, fuzzy=False, expand=True), questions, APPROX_RUNS),
               "approx_ms": mean_retrieval_ms(ApproxSearcher(idx, expand=True), questions,
                                              APPROX_RUNS)}
        rows.append(row)
        print("scaling", row, flush=True)
    return rows


# --------------------------------------------------------------------------- B
def grade(q, answer, chunks):
    """Mismos criterios que eval_stage5.classify."""
    context_ok = any(is_hit(q, c.__dict__) for c in chunks)
    if q.needle is None:
        return ("correct_abstention" if answer.abstained else "hallucinated"), context_ok
    if answer.abstained:
        return "abstained", context_ok
    ok = any(e in answer.text.lower() for e in q.expected)
    return ("correct" if ok else "wrong"), context_ok


def run_config(bot, retrieved, name, build_context):
    outcomes, ctx_words, model_ms, ctx_ok = [], [], [], 0
    for q, prompt, hits in retrieved:
        ctx_hits, text = build_context(q, hits)
        t0 = time.perf_counter()
        answer = bot.model.answer(prompt, text)
        model_ms.append((time.perf_counter() - t0) * 1000)
        outcome, context_ok = grade(q, answer, ctx_hits)
        outcomes.append((q, outcome))
        ctx_words.append(sum(len(h.text.split()) for h in ctx_hits))
        ctx_ok += context_ok and q.needle is not None
    answerable = [o for q, o in outcomes if q.needle is not None]
    unans = [o for q, o in outcomes if q.needle is None]
    row = {"config": name,
           "correct": answerable.count("correct"), "answerable": len(answerable),
           "wrong": answerable.count("wrong"), "abstained": answerable.count("abstained"),
           "context_has_answer": ctx_ok,
           "correct_abstention": unans.count("correct_abstention"), "unanswerable": len(unans),
           "hallucinated": unans.count("hallucinated"),
           "mean_context_words": round(statistics.mean(ctx_words), 1),
           "mean_model_ms": round(statistics.mean(model_ms))}
    print("context", row, flush=True)
    return row


def selected(max_chunks=4, max_words=320, redundancy=0.7):
    def build(q, hits):
        ctx = select_context(hits, max_words=max_words, max_chunks=max_chunks,
                             redundancy=redundancy)
        return ctx.chunks, ctx.text
    return build


def with_distractors(n, pool):
    def build(q, hits):
        ctx = select_context(hits)
        rng = random.Random(f"{SEED}-{q.question}-{n}")
        taken = {h.title for h in ctx.chunks}
        extra = [Hit(c["id"], c["title"], 0.0, {}, c["text"])
                 for c in rng.sample([c for c in pool if c["title"] not in taken], n)]
        mixed = ctx.chunks + extra
        rng.shuffle(mixed)
        return mixed, "\n\n".join(h.text for h in mixed)
    return build


def experiment_context(bot):
    retrieved = []
    for q in QUESTIONS:
        clean = clean_question(q.question, bot.approx)
        prompt, _ = rewrite_question(clean.text)
        retrieved.append((q, prompt, bot.approx.search(q.question, k=10).hits))
    pool = bot.index.chunks
    configs = [
        ("top-1 fragmento", selected(max_chunks=1)),
        ("top-2 fragmentos", selected(max_chunks=2)),
        ("top-3 fragmentos", selected(max_chunks=3)),
        ("top-4 (configuracion por defecto)", selected()),
        ("top-6, hasta 600 palabras", selected(max_chunks=6, max_words=600)),
        ("top-4 sin filtro de redundancia", selected(redundancy=1.01)),
        ("presupuesto 100 palabras", selected(max_chunks=6, max_words=100)),
        ("presupuesto 200 palabras", selected(max_chunks=6, max_words=200)),
        ("defecto + 2 fragmentos al azar", with_distractors(2, pool)),
        ("defecto + 4 fragmentos al azar", with_distractors(4, pool)),
    ]
    return [run_config(bot, retrieved, name, build) for name, build in configs]


def main():
    bot = ChatBot(cache=False)
    bot.answer("warm up", "approx")
    scaling = experiment_scaling(bot.index.chunks)
    context = experiment_context(bot)
    OUT.write_text(json.dumps({"scaling": scaling, "context_selection": context,
                               "scale_questions": [QUESTIONS[i].question for i in SCALE_QUESTIONS],
                               "seed": SEED}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
