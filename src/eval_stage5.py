"""Datos para el reporte de la etapa 5 (pipeline completo con el modelo de lenguaje).

Corre las preguntas de eval_questions.py en los dos modos (approx y exact) y guarda,
por pregunta: pregunta limpia, fragmentos elegidos, respuesta, confianza y tiempos.

Clasificacion de cada respuesta (solo preguntas con respuesta esperada):
  correct              la respuesta contiene alguna de las cadenas esperadas
  wrong_with_support   el contexto TENIA el fragmento correcto, pero el modelo fallo
  wrong_no_support     el contexto no tenia el fragmento correcto (recuperacion fallo)
  abstained_*          el modelo dijo "no se" (con o sin el fragmento correcto)
Para preguntas sin respuesta: correct_abstention o hallucinated (respondio algo).

Salida: data/stage5_results.json     Uso: python src/eval_stage5.py
"""
import json
import statistics

from eval_questions import QUESTIONS, is_hit
from index import CHUNKS_PATH
from pipeline import MODES, ChatBot

OUT = CHUNKS_PATH.parent / "stage5_results.json"


def classify(q, reply):
    context_ok = any(is_hit(q, c.__dict__) for c in reply.context.chunks)
    if q.needle is None:  # sin respuesta en el corpus
        return "correct_abstention" if reply.answer.abstained else "hallucinated", context_ok
    if reply.answer.abstained:
        return ("abstained_with_support" if context_ok else "abstained_no_support"), context_ok
    ok = any(e in reply.answer.text.lower() for e in q.expected)
    if ok:
        return "correct", context_ok
    return ("wrong_with_support" if context_ok else "wrong_no_support"), context_ok


def main():
    bot = ChatBot(cache=False)
    bot.answer("warm up", "approx")  # la primera inferencia incluye inicializaciones
    rows = {m: [] for m in MODES}
    per_question = {q.question: {"kind": q.kind, "expected": q.expected} for q in QUESTIONS}

    for q in QUESTIONS:
        for mode in MODES:
            r = bot.answer(q.question, mode)
            outcome, context_ok = classify(q, r)
            rows[mode].append({"kind": q.kind, "outcome": outcome, "context_ok": context_ok,
                               "answerable": q.needle is not None, **r.timings_ms,
                               "n_chunks": len(r.context.chunks)})
            per_question[q.question][mode] = {
                "prompt_question": r.prompt_question,
                "corrections": r.clean.corrections,
                "context": [{"id": c.id, "title": c.title, "score": c.score, "text": c.text}
                            for c in r.context.chunks],
                "skipped": r.context.skipped,
                "answer": r.answer.text, "confidence": round(r.answer.score, 3),
                "abstained": r.answer.abstained, "supporting_chunk": r.supporting_chunk,
                "outcome": outcome, "context_has_answer": context_ok,
                "timings_ms": r.timings_ms}
            print(f"[{mode:6}] {outcome:22} {q.question[:58]!r:60} -> {r.answer.text[:50]!r} "
                  f"({r.answer.score:.2f}) ret={r.timings_ms['retrieval']}ms")

    summary = {}
    for mode, rs in rows.items():
        answerable = [r for r in rs if r["answerable"]]
        unans = [r for r in rs if not r["answerable"]]
        count = lambda name, sub=rs: sum(1 for r in sub if r["outcome"] == name)
        summary[mode] = {
            "questions": len(rs), "answerable": len(answerable), "unanswerable": len(unans),
            "correct": count("correct"),
            "accuracy_answerable": round(count("correct") / len(answerable), 3),
            "wrong_with_support": count("wrong_with_support"),
            "wrong_no_support": count("wrong_no_support"),
            "abstained_with_support": count("abstained_with_support"),
            "abstained_no_support": count("abstained_no_support"),
            "correct_abstention": count("correct_abstention"),
            "hallucinated": count("hallucinated"),
            "context_contains_answer": sum(1 for r in answerable if r["context_ok"]),
            "mean_retrieval_ms": round(statistics.mean(r["retrieval"] for r in rs), 1),
            "mean_context_ms": round(statistics.mean(r["context"] for r in rs), 2),
            "mean_model_ms": round(statistics.mean(r["model"] for r in rs), 1),
            "mean_total_ms": round(statistics.mean(r["total"] for r in rs), 1),
            "mean_context_chunks": round(statistics.mean(r["n_chunks"] for r in rs), 2),
            "by_kind": {k: {"n": sum(1 for r in answerable if r["kind"] == k),
                            "correct": sum(1 for r in answerable
                                           if r["kind"] == k and r["outcome"] == "correct")}
                        for k in sorted({r["kind"] for r in answerable})},
        }
    print(json.dumps(summary, indent=1))
    OUT.write_text(json.dumps({"summary": summary, "per_question": per_question},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
