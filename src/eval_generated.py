"""Evaluacion con preguntas GENERADAS mecanicamente desde las fichas de la wiki.

Las 26 preguntas de eval_questions.py las escribio y ajusto el desarrollador, asi que no
miden como se comporta el sistema con cartas y preguntas que nadie reviso. Aqui las
preguntas salen de plantillas sobre cartas elegidas al azar (semilla fija) y la respuesta
esperada se lee del propio campo de la ficha: nada se ajusta a mano.

Plantillas (las mismas formas que un usuario escribiria):
  rarity  "What rarity is X?"        correcto si la respuesta contiene el valor de Rarity
  cost    "How much does X cost?"    correcto si contiene el numero de Buy Price
  effect  "What does X do?"          correcto si se solapa con el campo Effect (>= 0.6)
  unlock  "How do I unlock X?"       correcto si se solapa con Unlock Requirement (>= 0.6)

Cada pregunta se clasifica: correct / wrong / abstained, y se anota si la ficha de la carta
estaba en el contexto (separa "la busqueda fallo" de "el modelo se nego teniendo la ficha").

Salida: data/generated_results.json    Uso: python src/eval_generated.py [N_cartas] [modo]
"""
import json
import random
import re
import statistics
import sys
from collections import Counter

from index import CHUNKS_PATH
from pipeline import ChatBot
from preprocess import tokens

RAW = CHUNKS_PATH.parent / "raw" / "pages.json"
OUT = CHUNKS_PATH.parent / "generated_results.json"
SEED = 20261003
OVERLAP = 0.6
FIELDS = {"Rarity": "rarity", "Buy Price": "cost", "Effect": "effect",
          "Unlock Requirement": "unlock"}
TEMPLATES = {"rarity": "What rarity is {x}?", "cost": "How much does {x} cost?",
             "effect": "What does {x} do?", "unlock": "How do I unlock {x}?"}


def overlap_ok(answer, expected):
    a, e = set(tokens(answer)), set(tokens(expected))
    if not a or not e:
        return False
    common = len(a & e)
    return common / len(a) >= OVERLAP or common / len(e) >= OVERLAP


def is_correct(kind, answer, expected):
    if kind == "rarity":
        return expected.lower() in answer.lower()
    if kind == "cost":
        return re.search(rf"(?<!\d){re.escape(expected)}(?!\d)", answer) is not None
    return overlap_ok(answer, expected)


def build_questions(pages, n_cards, rng):
    jokers = [p for p in pages if p["category"] == "Jokers"]
    others = [p for p in pages if p["category"] in
              ("Tarot Cards", "Planet Cards", "Spectral Cards", "Vouchers")]
    cards = rng.sample(jokers, min(n_cards, len(jokers)))
    cards += rng.sample(others, min(max(n_cards // 3, 1), len(others)))
    questions = []
    for page in cards:
        fields = {FIELDS[k]: v for k, v in page["infobox"] if k in FIELDS}
        if "cost" in fields:
            digits = re.search(r"\d+", fields["cost"])
            fields["cost"] = digits.group() if digits else None
        for kind, expected in fields.items():
            if expected:
                questions.append({"card": page["title"], "category": page["category"],
                                  "kind": kind, "expected": expected,
                                  "question": TEMPLATES[kind].format(x=page["title"])})
    return questions


def main():
    n_cards = int(sys.argv[1]) if len(sys.argv) > 1 else 45
    mode = sys.argv[2] if len(sys.argv) > 2 else "approx"
    pages = json.loads(RAW.read_text(encoding="utf-8"))
    questions = build_questions(pages, n_cards, random.Random(SEED))
    bot = ChatBot(cache=False)
    bot.answer("warm up", mode)
    ficha = {}
    for c in bot.index.chunks:
        m = re.match(r"(.+?): \1 \(", c["text"])
        if m:
            ficha[m.group(1)] = c["id"]

    rows = []
    for i, q in enumerate(questions, 1):
        r = bot.answer(q["question"], mode)
        in_context = ficha.get(q["card"]) in {c.id for c in r.context.chunks}
        if r.answer.abstained:
            outcome = "abstained"
        else:
            outcome = "correct" if is_correct(q["kind"], r.answer.text, q["expected"]) else "wrong"
        rows.append({**q, "outcome": outcome, "ficha_in_context": in_context,
                     "answer": r.answer.text, "confidence": round(r.answer.score, 3),
                     "prompt": r.prompt_question, "total_ms": r.timings_ms["total"]})
        if i % 20 == 0:
            print(f"  {i}/{len(questions)}", flush=True)

    def pct(n, d):
        return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "-"

    print(f"\n{len(rows)} preguntas sobre {len({r['card'] for r in rows})} cartas, modo {mode}")
    total = Counter(r["outcome"] for r in rows)
    print("GLOBAL:", {k: pct(v, len(rows)) for k, v in total.items()})
    for kind in TEMPLATES:
        sub = [r for r in rows if r["kind"] == kind]
        c = Counter(r["outcome"] for r in sub)
        print(f"  {kind:7} n={len(sub):3}  correctas {pct(c['correct'], len(sub)):12} "
              f"erroneas {pct(c['wrong'], len(sub)):11} se abstuvo {pct(c['abstained'], len(sub))}")
    abst = [r for r in rows if r["outcome"] == "abstained"]
    print(f"\nDe las {len(abst)} abstenciones: la ficha SI estaba en el contexto en "
          f"{sum(r['ficha_in_context'] for r in abst)}; NO estaba en {sum(not r['ficha_in_context'] for r in abst)}")
    print(f"Ficha en el contexto, en todas las preguntas: "
          f"{pct(sum(r['ficha_in_context'] for r in rows), len(rows))}")
    print(f"Tiempo medio total: {statistics.mean(r['total_ms'] for r in rows):.0f} ms")
    OUT.write_text(json.dumps({"mode": mode, "seed": SEED, "rows": rows}, ensure_ascii=False,
                              indent=1), encoding="utf-8")
    print("->", OUT)


if __name__ == "__main__":
    main()
