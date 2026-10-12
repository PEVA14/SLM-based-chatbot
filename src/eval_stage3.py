"""Datos para el reporte de la etapa 3 (busqueda exacta).

Salida: data/stage3_results.json  (y un resumen en consola)
Uso:    python src/eval_stage3.py
"""
import json
import statistics
import time

from exact import ALGORITHMS
from index import CHUNKS_PATH, Index
from search_exact import ExactSearcher

OUT = CHUNKS_PATH.parent / "stage3_results.json"

# (pregunta, pagina esperada, texto que debe contener el fragmento con la respuesta, por que)
QUESTIONS = [
    ("What rarity is Blueprint?", "Blueprint", "Rarity: Rare",
     "palabras de la pregunta == palabras de la wiki"),
    ("How do I unlock Hologram?", "Hologram", "Unlock Requirement:",
     "nombre de carta + palabra de la ficha"),
    ("What does The Fool tarot card do?", "The Fool", "Effect: Creates the last Tarot",
     "nombre con stopword ('the fool')"),
    ("Which joker copies the ability of the joker to its right?", "Blueprint",
     "Effect: Copies ability of Joker to the right", "sin nombre: depende de palabras compartidas"),
    ("How much does Mr. Bones cost?", "Mr. Bones", "Buy Price:",
     "sinonimo: 'cost' vs 'Buy Price'"),
    ("What does Blueprnt do?", "Blueprint", "Effect: Copies ability", "typo en el nombre"),
    ("Which jokers give X1.5 Mult?", None, None, "simbolo de juego como termino"),
    ("Does the game have a joker called Pikachu?", None, None, "sin respuesta en el corpus"),
]
MICRO_PATTERNS = ["mult", "blueprint", "mr bones", "x1.5"]
RUNS = 3


def median_ms(fn, runs=RUNS):
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return round(statistics.median(times), 1)


def main():
    idx = Index.load()
    # Etapa 3 original: sin equivalencias de dominio (estas se miden en eval_stage4.py).
    kmp = ExactSearcher(idx, term_algo="kmp", expand=False)
    zed = ExactSearcher(idx, term_algo="z", expand=False)

    questions = []
    for q, gold, needle, why in QUESTIONS:
        res = kmp.search(q, k=50)
        res_z = zed.search(q, k=50)
        answer_rank = next((i for i, h in enumerate(res.hits, 1)
                            if h.title == gold and needle in h.text), None) if gold else None
        questions.append({
            "question": q, "why": why, "gold_page": gold,
            "terms": res.terms, "unmatched_terms": res.unmatched_terms, "names": res.names,
            "patterns_scanned": res.patterns_scanned, "chars_scanned": res.chars_scanned,
            "time_ms_kmp": res.timings_ms["total"], "time_ms_z": res_z.timings_ms["total"],
            "same_ranking_kmp_z": [h.id for h in res.hits] == [h.id for h in res_z.hits],
            "answer_chunk_rank": answer_rank,
            "hits": [{"rank": i, "id": h.id, "title": h.title, "score": h.score,
                      "matched": h.matched, "text": h.text[:240]}
                     for i, h in enumerate(res.hits[:5], 1)],
        })
        print(f"{q!r}: kmp {res.timings_ms['total']} ms, z {res_z.timings_ms['total']} ms, "
              f"answer chunk rank={answer_rank}")

    corpus = kmp.corpus
    micro = []
    for pat in MICRO_PATTERNS:
        padded = f" {pat} "
        row = {"pattern": pat, "matches": len(ALGORITHMS["kmp"](corpus, padded))}
        for name, fn in ALGORITHMS.items():
            row[f"{name}_ms"] = median_ms(lambda fn=fn: fn(corpus, padded))
        micro.append(row)
        print("micro", row)

    scaling = []
    chunks = idx.chunks
    for frac in (0.25, 0.5, 0.75, 1.0):
        sub = ExactSearcher(Index(chunks[: int(len(chunks) * frac)]))
        row = {"chunks": sub.n, "corpus_chars": len(sub.corpus)}
        for name in ("kmp", "z"):
            algo = ALGORITHMS[name]
            row[f"{name}_ms_per_term"] = median_ms(lambda a=algo: [a(sub.corpus, f" {p} ") for p in
                                                                   ("mult", "joker", "card")]) / 3
            row[f"{name}_ms_per_term"] = round(row[f"{name}_ms_per_term"], 1)
        scaling.append(row)
        print("scaling", row)

    OUT.write_text(json.dumps({"questions": questions, "micro_benchmark": micro,
                               "scaling": scaling,
                               "corpus": {"chunks": idx.stats()["chunks"],
                                          "chars": len(corpus)}},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
