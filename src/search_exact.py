"""Etapa 3b: recuperacion por busqueda exacta (KMP + Z-function).

Pipeline:
  pregunta -> tokens/terminos -> nombres de carta mencionados (Z/KMP sobre la pregunta)
           -> barrido del corpus con KMP por cada termino y Z por cada frase
           -> puntuacion BM25 por fragmento -> top-k

Las coincidencias son por *palabra completa*: el corpus es " tok tok tok " por
fragmento, y se busca " termino " (con espacios), asi "mult" no coincide con
"multiplier" ni "joker" con "jokers". Es la limitacion central de la busqueda exacta.

Puntuacion de un fragmento c (patrones p = terminos y frases):
    score(c) = sum_p  w_p * f(tf_pc) + bonus_titulo(c)
    f(tf)    = tf (K1+1) / (tf + K1 (1 - B + B len_c/len_prom))     (saturacion BM25)
    w_p      = idf_p = ln(1 + (N - df_p + .5)/(df_p + .5))          (x PHRASE_BOOST si es frase)
    bonus    = TITLE_BONUS * idf(nombre) si el fragmento pertenece a la pagina de la
               carta mencionada.
tf y df salen de lo que encuentran KMP/Z, no del indice invertido.

Complejidad por consulta con k patrones y corpus de T caracteres:
  barrido      O(k * (T + m))   (KMP y Z son lineales en texto + patron)
  deteccion    O(C * (q + L))   C nombres de carta, q = |pregunta|, L = |nombre|
  puntuacion   O(P) con P = total de ocurrencias encontradas
"""
import sys
import time
from bisect import bisect_right
from dataclasses import dataclass, field

from exact import ALGORITHMS
from index import Index
from lexicon import EXPANSION_WEIGHT, QUERY_STOPWORDS, expansions
from preprocess import STOPWORDS, joined, tokens
from scoring import idf, tf_saturation

PHRASE_BOOST = 2.0
TITLE_BONUS = 1.0


@dataclass
class Hit:
    id: int
    title: str
    score: float
    matched: dict
    text: str


@dataclass
class SearchResult:
    question: str
    terms: list
    unmatched_terms: list
    names: list
    hits: list
    timings_ms: dict = field(default_factory=dict)
    patterns_scanned: int = 0
    chars_scanned: int = 0
    expanded: list = field(default_factory=list)  # terminos anadidos por lexicon.py
    variants: dict = field(default_factory=dict)  # busqueda aproximada: termino -> variantes
    chunks_examined: int = 0  # fragmentos que la busqueda tuvo que mirar


class ExactSearcher:
    def __init__(self, index: Index, term_algo="kmp", phrase_algo="z", cache=False, expand=True):
        """cache=True memoriza el barrido de cada patron (la GUI); los benchmarks lo apagan.
        expand=True anade las equivalencias de dominio de lexicon.py."""
        self.expand = expand
        self.index = index
        self._cache = {} if cache else None
        self.term_search = ALGORITHMS[term_algo]
        self.phrase_search = ALGORITHMS[phrase_algo]
        self.n = len(index.chunks)
        padded = [f" {j} " for j in index.joined]
        self.corpus = "\n".join(padded)
        self.starts, offset = [], 0
        for p in padded:
            self.starts.append(offset)
            offset += len(p) + 1
        self.lengths = [len(j.split()) for j in index.joined]
        self.avg_len = sum(self.lengths) / self.n
        self.names = [name for name, _ in index.names.items()]
        self.by_title = {}
        for c in index.chunks:
            self.by_title.setdefault(joined(c["title"]), []).append(c["id"])

    # -- barrido -------------------------------------------------------------
    def _scan(self, pattern, algo):
        """{id_fragmento: ocurrencias} de ` pattern ` como palabra(s) completa(s)."""
        if self._cache is not None and pattern in self._cache:
            return self._cache[pattern]
        tf = {}
        for pos in algo(self.corpus, f" {pattern} "):
            cid = bisect_right(self.starts, pos) - 1
            tf[cid] = tf.get(cid, 0) + 1
        if self._cache is not None:
            self._cache[pattern] = tf
        return tf

    def detect_names(self, question):
        """Nombres de carta presentes en la pregunta (los mas largos ganan solapes)."""
        q = f" {joined(question)} "
        spans = []
        for name in self.names:
            pat = f" {name} "
            for pos in self.phrase_search(q, pat):
                spans.append((pos + 1, pos + 1 + len(name), name))
        spans.sort(key=lambda s: s[0] - s[1])  # mas largos primero
        kept = []
        for start, end, name in spans:
            if all(end <= s or start >= e for s, e, _ in kept) and name not in STOPWORDS:
                kept.append((start, end, name))
        return [name for _, _, name in sorted(kept)]

    # -- busqueda ------------------------------------------------------------
    def search(self, question, k=5):
        t0 = time.perf_counter()
        toks = tokens(question)
        qterms = list(dict.fromkeys(t for t in toks if t not in STOPWORDS and t not in QUERY_STOPWORDS))
        names = self.detect_names(question)
        t_detect = time.perf_counter()

        # Un termino fuera del vocabulario (Trie) no puede coincidir: se evita el barrido.
        known = [t for t in qterms if t in self.index.vocab]
        unmatched = [t for t in qterms if t not in self.index.vocab]
        extra = [t for t in expansions(question, qterms) if t in self.index.vocab] \
            if self.expand else []
        patterns = {t: (self._scan(t, self.term_search), 1.0) for t in known}
        patterns.update({t: (self._scan(t, self.term_search), EXPANSION_WEIGHT) for t in extra})
        t_terms = time.perf_counter()
        phrases = [n for n in names if " " in n]
        for ph in phrases:
            patterns[ph] = (self._scan(ph, self.phrase_search), PHRASE_BOOST)
        t_phrases = time.perf_counter()
        if not any(patterns[t][0] for t in known + phrases):
            patterns = {}  # solo equivalencias: sin evidencia propia de la pregunta, no hay hits

        scores, matched = {}, {}
        for pat, (tf, weight) in patterns.items():
            rarity = idf(len(tf), self.n)
            for cid, f in tf.items():
                norm = tf_saturation(f, self.lengths[cid], self.avg_len)
                scores[cid] = scores.get(cid, 0.0) + weight * rarity * norm
                matched.setdefault(cid, {})[pat] = f
        for name in names:
            tf = patterns.get(name, (None,))[0]
            if tf is None:
                continue  # nombre de una palabra que no esta en el vocabulario
            rarity = idf(len(tf), self.n)
            for cid in self.by_title.get(name, ()):
                scores[cid] = scores.get(cid, 0.0) + TITLE_BONUS * rarity
        t_score = time.perf_counter()

        top = sorted(scores, key=lambda c: (-scores[c], c))[:k]
        hits = [Hit(c, self.index.chunks[c]["title"], round(scores[c], 3),
                    matched.get(c, {}), self.index.chunks[c]["text"]) for c in top]
        ms = lambda a, b: round((b - a) * 1000, 2)
        return SearchResult(
            question=question, terms=qterms, unmatched_terms=unmatched, names=names,
            hits=hits,
            timings_ms={"total": ms(t0, t_score), "detect_names": ms(t0, t_detect),
                        "scan_terms": ms(t_detect, t_terms),
                        "scan_phrases": ms(t_terms, t_phrases),
                        "scoring": ms(t_phrases, t_score)},
            patterns_scanned=len(patterns),
            chars_scanned=len(patterns) * len(self.corpus), expanded=extra,
            chunks_examined=self.n)


def show(res, snippet=150):
    print(f"\nPregunta: {res.question}")
    print(f"  terminos : {res.terms}   sin coincidencia posible: {res.unmatched_terms}")
    if res.expanded:
        print(f"  anadidos : {res.expanded}  (equivalencias de dominio)")
    for term, vs in res.variants.items():
        print(f"  variantes: {term} -> {[(w, sim, src) for w, sim, src in vs]}")
    print(f"  cartas   : {res.names}")
    for rank, h in enumerate(res.hits, 1):
        print(f"  #{rank} [{h.score:7.3f}] {h.title} (frag {h.id})  {h.matched}")
        print(f"       {h.text[:snippet]}...")
    parts = ", ".join(f"{k} {v}" for k, v in res.timings_ms.items() if k != "total")
    print(f"  tiempo   : {res.timings_ms['total']} ms  ({parts}); "
          f"fragmentos examinados: {res.chunks_examined}")


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "What rarity is Blueprint?"
    show(ExactSearcher(Index.load()).search(question))
