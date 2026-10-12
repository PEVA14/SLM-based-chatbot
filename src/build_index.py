"""Construye el indice y mide su costo (datos para el reporte, etapa 2).

Salida: data/vocab.txt (palabra<TAB>frecuencia) y data/index_stats.json
Uso:    python src/build_index.py
"""
import json
import time
import tracemalloc
from pathlib import Path

from index import CHUNKS_PATH, Index
from preprocess import STOPWORDS

DATA = CHUNKS_PATH.parent
FRACTIONS = (0.25, 0.5, 0.75, 1.0)
REPEATS = 3


def timed_build(chunks):
    best = float("inf")
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        idx = Index(chunks)
        best = min(best, time.perf_counter() - t0)
    return idx, best


def main():
    chunks = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))

    tracemalloc.start()
    idx = Index(chunks)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    scaling = []
    for f in FRACTIONS:
        sub = chunks[: int(len(chunks) * f)]
        sub_idx, secs = timed_build(sub)
        scaling.append({"chunks": len(sub), "tokens": sub_idx.total_tokens,
                        "build_ms": round(secs * 1000, 1)})

    stats = idx.stats()
    stats["stopwords_in_list"] = len(STOPWORDS)
    stats["build_ms_full"] = scaling[-1]["build_ms"]
    stats["peak_memory_mb"] = round(peak / 1e6, 1)
    stats["scaling"] = scaling
    (DATA / "index_stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")

    vocab = idx.vocabulary()
    (DATA / "vocab.txt").write_text(
        "".join(f"{w}\t{n}\n" for w, n in vocab), encoding="utf-8")

    print(json.dumps(stats, indent=1))
    top = sorted(vocab, key=lambda wc: -wc[1])[:15]
    print("terminos mas frecuentes:", top)
    print("autocomplete 'mu':", idx.vocab.complete("mu", 6))


if __name__ == "__main__":
    main()
