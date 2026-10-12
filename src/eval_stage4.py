"""Datos para el reporte de la etapa 4 (busqueda aproximada vs exacta).

Configuraciones (aislan que aporta cada pieza):
  exact_kmp       Etapa 3 tal cual: barrido KMP/Z, sin equivalencias.
  exact_kmp_lex   Etapa 3 + equivalencias de dominio (lexicon.py).
  exact_index     Coincidencia exacta usando el indice invertido (misma
                  infraestructura que la aproximada, sin tolerancia a errores).
  approx_nolex    Aproximada (Levenshtein/Trie + trigramas/Jaccard), sin equivalencias.
  approx          Aproximada + equivalencias (la configuracion completa).

Metricas sobre las preguntas con respuesta: hit@k (el fragmento con la respuesta esta
entre los k primeros), MRR, tiempo medio y fragmentos examinados.
Salida: data/stage4_results.json
Uso:    python src/eval_stage4.py
"""
import json
import statistics
import time

from approx import levenshtein
from eval_questions import QUESTIONS, is_hit, validate
from index import CHUNKS_PATH, Index
from search_approx import ApproxSearcher
from search_exact import ExactSearcher

OUT = CHUNKS_PATH.parent / "stage4_results.json"
K = 50
FAST_RUNS = 5
MICRO_TERMS = ["blueprnt", "hologrm", "jokers", "retrigger", "multiplyer", "fibonaci",
               "brainstrom", "cost"]


def run(searcher, q, fast):
    """Ejecuta la busqueda; si es rapida repite y reporta la mediana del tiempo."""
    res = searcher.search(q.question, k=K)
    if fast:
        times = [res.timings_ms["total"]]
        times += [searcher.search(q.question, k=K).timings_ms["total"] for _ in range(FAST_RUNS - 1)]
        res.timings_ms["total"] = round(statistics.median(times), 2)
    return res


def answer_rank(q, hits):
    return next((i for i, h in enumerate(hits, 1) if is_hit(q, h.__dict__)), None)


def summarize(rows):
    answerable = [r for r in rows if r["rank_available"]]
    n = len(answerable)

    def hit(k, subset=answerable):
        return round(sum(1 for r in subset if r["rank"] and r["rank"] <= k) / len(subset), 3) \
            if subset else None

    by_kind = {}
    for kind in sorted({r["kind"] for r in answerable}):
        sub = [r for r in answerable if r["kind"] == kind]
        by_kind[kind] = {"n": len(sub), "hit@1": hit(1, sub), "hit@3": hit(3, sub)}
    unanswerable = [r for r in rows if not r["rank_available"]]
    return {
        "answerable_questions": n,
        "hit@1": hit(1), "hit@3": hit(3), "hit@5": hit(5),
        "mrr": round(sum(1 / r["rank"] for r in answerable if r["rank"]) / n, 3),
        "mean_time_ms": round(statistics.mean(r["time_ms"] for r in rows), 1),
        "median_time_ms": round(statistics.median(r["time_ms"] for r in rows), 1),
        "mean_chunks_examined": round(statistics.mean(r["chunks_examined"] for r in rows)),
        "by_kind": by_kind,
        "unanswerable_returned_hits": sum(1 for r in unanswerable if r["n_hits"] > 0),
        "unanswerable_total": len(unanswerable),
    }


def micro_fuzzy(idx):
    words = [w for w, _ in idx.vocabulary()]
    rows = []
    for term in MICRO_TERMS:
        d = 1 if len(term) <= 7 else 2
        t0 = time.perf_counter()
        trie_found = idx.vocab.fuzzy(term, d, fixed_prefix=1)
        t_trie = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        brute = [w for w in words if w[0] == term[0] and levenshtein(term, w) <= d]
        t_brute = (time.perf_counter() - t0) * 1000
        rows.append({"term": term, "max_dist": d, "trie_ms": round(t_trie, 2),
                     "brute_force_ms": round(t_brute, 2),
                     "speedup": round(t_brute / t_trie, 1),
                     "same_result": sorted(w for w, _, _ in trie_found) == sorted(brute),
                     "found": [(w, dist) for w, dist, _ in trie_found[:5]]})
    return rows


def main():
    idx = Index.load()
    bad = validate(idx.chunks)
    assert not bad, f"etiquetas inalcanzables: {bad}"

    configs = {
        "exact_kmp": (ExactSearcher(idx, expand=False), False),
        "exact_kmp_lex": (ExactSearcher(idx, expand=True), False),
        "exact_index": (ApproxSearcher(idx, fuzzy=False, expand=True), True),
        "approx_nolex": (ApproxSearcher(idx, fuzzy=True, expand=False), True),
        "approx": (ApproxSearcher(idx, fuzzy=True, expand=True), True),
    }
    results = {}
    per_question = {q.question: {"kind": q.kind, "page": q.page, "needle": q.needle,
                                 "configs": {}} for q in QUESTIONS}
    for name, (searcher, fast) in configs.items():
        rows = []
        for q in QUESTIONS:
            res = run(searcher, q, fast)
            rank = answer_rank(q, res.hits)
            rows.append({"question": q.question, "kind": q.kind, "rank": rank,
                         "rank_available": q.needle is not None,
                         "time_ms": res.timings_ms["total"],
                         "chunks_examined": res.chunks_examined, "n_hits": len(res.hits)})
            per_question[q.question]["configs"][name] = {
                "answer_rank": rank, "time_ms": res.timings_ms["total"],
                "terms": res.terms, "unmatched_terms": res.unmatched_terms,
                "names": res.names, "expanded": res.expanded, "variants": res.variants,
                "top3": [{"id": h.id, "title": h.title, "score": h.score,
                          "matched": h.matched} for h in res.hits[:3]]}
        results[name] = summarize(rows)
        s = results[name]
        print(f"{name:14} hit@1={s['hit@1']} hit@3={s['hit@3']} hit@5={s['hit@5']} "
              f"mrr={s['mrr']} mean={s['mean_time_ms']}ms examined={s['mean_chunks_examined']} "
              f"noans_with_hits={s['unanswerable_returned_hits']}/{s['unanswerable_total']}")

    micro = micro_fuzzy(idx)
    for row in micro:
        print("micro", row["term"], f"trie {row['trie_ms']}ms vs fuerza bruta "
              f"{row['brute_force_ms']}ms ({row['speedup']}x) igual={row['same_result']}")

    OUT.write_text(json.dumps({"summary": results, "per_question": per_question,
                               "trie_fuzzy_micro": micro, "k": K},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
