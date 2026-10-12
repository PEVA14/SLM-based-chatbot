"""Etapa 5c: modelo de lenguaje preentrenado (sin entrenamiento propio).

deepset/roberta-base-squad2 (Hugging Face, licencia CC-BY-4.0): modelo *extractivo* de
preguntas y respuestas. No genera texto: elige el tramo del contexto que responde la
pregunta. Fue entrenado en SQuAD 2.0, que incluye preguntas sin respuesta, asi que con
handle_impossible_answer=True puede decir "no hay respuesta en el contexto".
"""
import os
import re
from dataclasses import dataclass

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

MODEL = "deepset/roberta-base-squad2"
NO_ANSWER = "I don't know: the selected context does not answer this question."


_TITLE_PREFIX = re.compile(r"^(?P<t>.+?): (?P=t)(?P<rest>\b.*)$", re.S)


def tidy_answer(text):
    """Quita el prefijo repetido "Titulo: Titulo" que todos los fragmentos llevan al inicio
    ("Mime: Mime" -> "Mime"); si el tramo no lo tiene, no cambia."""
    m = _TITLE_PREFIX.match(text)
    return (m["t"] + m["rest"]).strip() if m else text


@dataclass
class Answer:
    text: str            # tramo del contexto, o NO_ANSWER
    score: float         # confianza del modelo en [0, 1]
    start: int           # posicion del tramo en el contexto (-1 si se abstiene)
    end: int
    abstained: bool


class QAModel:
    def __init__(self, model=MODEL, min_score=0.0):
        """min_score: por debajo de este puntaje la respuesta se descarta (0 = confiar
        solo en la decision de abstencion del propio modelo)."""
        from transformers import pipeline
        self.min_score = min_score
        self.pipe = pipeline("question-answering", model=model, tokenizer=model, device=-1)

    def answer(self, question, context):
        if not context.strip():
            return Answer(NO_ANSWER, 0.0, -1, -1, True)
        out = self.pipe(question=question, context=context, handle_impossible_answer=True)
        text = tidy_answer(out["answer"].strip())
        if not text or out["score"] < self.min_score:
            return Answer(NO_ANSWER, float(out["score"]), -1, -1, True)
        return Answer(text, float(out["score"]), out["start"], out["end"], False)
