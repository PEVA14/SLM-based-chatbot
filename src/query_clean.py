"""Etapa 5a: limpieza de la pregunta antes de dar el prompt al modelo.

El modelo (roberta-base-squad2) es sensible a la ortografia: con "Blueprnt" no sabe
que se habla de la carta Blueprint. La limpieza usa las mismas herramientas de cadenas
de las etapas 2 y 4 para corregir el texto *original* (se conservan mayusculas y
puntuacion):

  1. Nombres de carta mal escritos ("Mr. Bone" -> "Mr. Bones") por Levenshtein sobre
     el Trie de nombres (ApproxSearcher.detect_name_spans).
  2. Palabras sueltas que no existen en el vocabulario ("Hologrm" -> "Hologram") por
     Levenshtein sobre el Trie del vocabulario (ApproxSearcher.resolve).

Solo se corrige lo que tiene una correccion clara (similitud >= MIN_FIX_SIM, palabra de al
menos MIN_FIX_LEN letras); lo demas se deja intacto. Las palabras que existen en el corpus nunca se tocan.
"""
import re
from dataclasses import dataclass, field

from preprocess import STOPWORDS, tokens
from search_approx import ApproxSearcher

MIN_FIX_SIM = 0.75
MIN_FIX_LEN = 6  # las palabras cortas tienen muchas vecinas a distancia 1: "hello" -> "hell"
_EDGES = re.compile(r"^(\W*)(.*?)(\W*)$", re.S)


@dataclass
class CleanQuestion:
    original: str
    text: str
    corrections: list = field(default_factory=list)  # [(original, corregido)]


def _match_case(original, fixed):
    return fixed.capitalize() if original[:1].isupper() else fixed


def clean_question(question, searcher: ApproxSearcher):
    words = question.split()
    spans, pos = [], 0  # rango de tokens [ini, fin) de cada palabra cruda
    for w in words:
        n = len(tokens(w))
        spans.append((pos, pos + n))
        pos += n

    out = list(words)
    keep = [True] * len(words)
    done = set()  # palabras ya corregidas por el paso 1
    corrections = []

    # 1. nombres de carta con errores -> titulo canonico
    for name, sim, i, j in searcher.detect_name_spans(question):
        covered = [k for k, (a, b) in enumerate(spans) if a < j and b > i]
        if sim >= 1.0 or not covered:
            continue
        first, last = covered[0], covered[-1]
        title = searcher.canonical_title(name)
        out[first] = title + _EDGES.match(words[last]).group(3)
        for k in covered[1:]:
            keep[k] = False
        done.update(covered)
        corrections.append((" ".join(words[first:last + 1]).strip("?!.,"), title))

    # 2. palabras sueltas que no existen en el vocabulario -> variante Levenshtein
    vocab = searcher.index.vocab
    for k, word in enumerate(words):
        if k in done:
            continue
        lead, core, tail = _EDGES.match(word).groups()
        toks = tokens(core)
        if len(toks) != 1 or toks[0] in vocab or toks[0] in STOPWORDS or len(toks[0]) < MIN_FIX_LEN \
                or any(ch.isdigit() for ch in toks[0]):
            continue
        variants = [v for v in searcher.resolve(toks[0]) if v.source == "levenshtein"]
        if variants and variants[0].sim >= MIN_FIX_SIM:
            fixed = _match_case(core, variants[0].word)
            out[k] = lead + fixed + tail
            corrections.append((core, fixed))

    text = " ".join(w for w, kept in zip(out, keep) if kept)
    return CleanQuestion(question, text, corrections)
