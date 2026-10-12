"""Etapa 4b: recuperacion por busqueda aproximada.

Tecnicas:
  1. Levenshtein sobre el Trie del vocabulario (Trie.fuzzy): variantes a distancia
     <= d de cada termino de la pregunta (plurales, conjugaciones, typos).
  2. Trigramas de caracteres + Jaccard (NgramIndex): respaldo para terminos sin
     ninguna variante Levenshtein, y para letras mal escritas en palabras largas.
  Ambas tambien resuelven nombres de carta con errores ("mr bone", "blueprnt").

Similitud (sim, en [0, 1]) de un termino de la pregunta t con una palabra del corpus v:
    Levenshtein:  sim = 1 - dist(t, v) / max(|t|, |v|)
    Trigramas:    sim = Jaccard(trigramas(t), trigramas(v))
  El peso de una variante es sim; las variantes de un termino que *si* existe en el
  vocabulario deben tener sim >= MIN_SIM_KNOWN (mas estricto: ya hay coincidencia
  exacta, solo se buscan plurales/conjugaciones), y las de un termino desconocido
  sim >= MIN_SIM_UNKNOWN (rescatar typos).

Puntuacion (misma formula que la busqueda exacta, ver scoring.py):
    best_t(c) = max_v sim(t, v) * f(tf_vc)                 mejor variante del termino en c
    score(c)  = sum_t w_t * idf(df_t) * best_t(c) + bonus_titulo(c)
  df_t es el numero de fragmentos que contienen *alguna* variante de t.
  Se toma el maximo (no la suma) para no contar dos veces "joker" y "jokers".
  tf y fragmentos candidatos salen de la tabla hash invertida de la etapa 2, no de
  recorrer el corpus: solo se tocan los fragmentos que contienen alguna variante.

Complejidad por consulta (k terminos, V vocabulario, P_v = |postings(v)|):
  resolver variantes  O(k * nodos_visitados_en_el_Trie * |t|) + O(k * trigramas*bucket)
  puntuar             O(sum_v P_v)  sobre las variantes aceptadas
  (la busqueda exacta barre T caracteres por termino; esta solo toca candidatos)
"""
import sys
import time
from dataclasses import dataclass

from approx import NgramIndex
from index import Index
from lexicon import EXPANSION_WEIGHT, QUERY_STOPWORDS, expansions
from preprocess import STOPWORDS, tokens
from scoring import idf, tf_saturation
from search_exact import PHRASE_BOOST, TITLE_BONUS, Hit, SearchResult, show

MIN_SIM_KNOWN = 0.8
MIN_SIM_UNKNOWN = 0.6
JACCARD_THRESHOLD = 0.4
MAX_VARIANTS = 4
MIN_NAME_SIM = 0.8
MAX_NAME_TOKENS = 4


@dataclass
class Variant:
    word: str
    sim: float
    source: str  # "exact" | "levenshtein" | "trigram"


def is_inflection(term, word):
    """Plural/conjugacion probable: una palabra es la otra mas un sufijo
    (joker/jokers, retrigger/retriggered) o cambia y -> ies (copy/copies).
    Excluye vecinos que solo difieren por una letra (joker/jokes, played/player)."""
    short, long_ = sorted((term, word), key=len)
    if len(short) == len(long_):
        return False
    if long_.startswith(short):
        return True
    return short.endswith("y") and long_.startswith(short[:-1] + "i")


def max_dist(length):
    """Ediciones permitidas segun la longitud: palabras cortas no toleran errores."""
    return 0 if length <= 3 else 1 if length <= 7 else 2


class ApproxSearcher:
    def __init__(self, index: Index, expand=True, fuzzy=True):
        """fuzzy=False desactiva toda tolerancia a errores: queda una busqueda exacta
        que usa el indice invertido (linea base para aislar el efecto de lo aproximado)."""
        self.index = index
        self.expand = expand
        self.fuzzy = fuzzy
        self.n = len(index.chunks)
        self.lengths = [len(j.split()) for j in index.joined]
        self.avg_len = sum(self.lengths) / self.n
        self.ngrams = NgramIndex(w for w, _ in index.vocabulary())
        self.by_title = {}
        for c in index.chunks:
            self.by_title.setdefault(" ".join(tokens(c["title"])), []).append(c["id"])

    def canonical_title(self, name):
        """Titulo original (con mayusculas y puntuacion) de un nombre normalizado."""
        return self.index.chunks[self.by_title[name][0]]["title"]

    # -- 1. variantes de un termino ------------------------------------------
    def resolve(self, term, exact_only=False):
        vocab = self.index.vocab
        known = term in vocab
        variants = [Variant(term, 1.0, "exact")] if known else []
        if exact_only or not self.fuzzy or any(ch.isdigit() for ch in term):
            return variants
        floor = MIN_SIM_KNOWN if known else MIN_SIM_UNKNOWN
        d = max_dist(len(term))
        found = []
        if d:
            for word, dist, freq in vocab.fuzzy(term, d, fixed_prefix=1):
                sim = 1 - dist / max(len(term), len(word))
                if dist and sim >= floor and not any(ch.isdigit() for ch in word) \
                        and (not known or is_inflection(term, word)):
                    found.append(Variant(word, round(sim, 3), "levenshtein"))
        if not known and not found and len(term) >= 4:
            for word, jac in self.ngrams.similar(term, JACCARD_THRESHOLD):
                if not any(ch.isdigit() for ch in word):
                    found.append(Variant(word, round(jac, 3), "trigram"))
        found.sort(key=lambda v: (-v.sim, -vocab.get(v.word)))
        return variants + found[:MAX_VARIANTS]

    # -- 2. nombres de carta con tolerancia a errores -------------------------
    def detect_names(self, question):
        """[(nombre, sim)] de cartas mencionadas, aun con typos; sin solapes."""
        return [(name, sim) for name, sim, _, _ in self.detect_name_spans(question)]

    def detect_name_spans(self, question):
        """[(nombre, sim, i, j)]: como detect_names, con el rango de tokens [i, j)."""
        toks = tokens(question)
        names, vocab = self.index.names, self.index.vocab
        cands = []  # (inicio, fin, nombre, sim)
        for i in range(len(toks)):
            for j in range(i + 1, min(i + MAX_NAME_TOKENS, len(toks)) + 1):
                gram = toks[i:j]
                if all(t in STOPWORDS for t in gram):
                    continue
                text = " ".join(gram)
                if names.get(text):
                    cands.append((i, j, text, 1.0))
                    continue
                if not self.fuzzy or len(text) < 5 or (j - i == 1 and text in vocab) \
                        or any(ch.isdigit() for ch in text):
                    continue
                d = 1 if len(text) <= 11 else 2
                best = names.fuzzy(text, d, fixed_prefix=1)
                if best:
                    name, dist, _ = best[0]
                    sim = 1 - dist / max(len(text), len(name))
                    if sim >= MIN_NAME_SIM:
                        cands.append((i, j, name, round(sim, 3)))
        cands.sort(key=lambda c: (-(c[1] - c[0]), -c[3], c[0]))
        taken, kept = set(), []
        for i, j, name, sim in cands:
            if not taken & set(range(i, j)):
                taken |= set(range(i, j))
                kept.append((i, j, name, sim))
        return [(name, sim, i, j) for i, j, name, sim in sorted(kept)]

    # -- 3. busqueda -----------------------------------------------------------
    def _best_per_chunk(self, variants):
        """{cid: (mejor valor sim*tf_sat, variante)} sobre las variantes dadas."""
        best = {}
        for v in variants:
            for cid, f in self.index.postings.get(v.word, {}).items():
                val = v.sim * tf_saturation(f, self.lengths[cid], self.avg_len)
                if cid not in best or val > best[cid][0]:
                    best[cid] = (val, v.word)
        return best

    def search(self, question, k=5):
        t0 = time.perf_counter()
        toks = tokens(question)
        qterms = list(dict.fromkeys(t for t in toks if t not in STOPWORDS and t not in QUERY_STOPWORDS))
        names = self.detect_names(question)
        t_names = time.perf_counter()

        weighted = {t: (self.resolve(t), 1.0) for t in qterms}
        extra = [t for t in expansions(question, qterms) if t in self.index.vocab] \
            if self.expand else []
        weighted.update({t: (self.resolve(t, exact_only=True), EXPANSION_WEIGHT) for t in extra})
        # Nombres corregidos: sus palabras puntuan aunque el typo cayera en una stopword.
        phrases = {}
        for name, sim in names:
            name_terms = [t for t in name.split() if t not in STOPWORDS]
            if len(name_terms) == 1 and name_terms[0] not in weighted:
                weighted[name_terms[0]] = (self.resolve(name_terms[0], exact_only=True), sim)
            elif len(name_terms) > 1:
                phrases[name] = (name_terms, sim)
        t_resolve = time.perf_counter()

        scores, matched, dfs = {}, {}, {}
        for term, (variants, weight) in weighted.items():
            best = self._best_per_chunk(variants)
            dfs[term] = len(best)
            rarity = idf(len(best), self.n)
            for cid, (val, word) in best.items():
                scores[cid] = scores.get(cid, 0.0) + weight * rarity * val
                matched.setdefault(cid, {})[term if word == term else f"{term}~{word}"] = 1
        name_df = {}
        for name, (name_terms, sim) in phrases.items():
            lists = [self.index.postings.get(t, {}) for t in name_terms]
            common = set.intersection(*(set(p) for p in lists)) if all(lists) else set()
            name_df[name] = len(common)
            rarity = idf(len(common), self.n)
            for cid in common:
                f = min(p[cid] for p in lists)
                val = PHRASE_BOOST * sim * rarity * tf_saturation(f, self.lengths[cid], self.avg_len)
                scores[cid] = scores.get(cid, 0.0) + val
                matched.setdefault(cid, {})[name] = f
        if not any(dfs[t] for t in qterms) and not any(name_df.values()):
            scores = {}  # solo equivalencias: sin evidencia propia de la pregunta, no hay hits
        for name, sim in names:
            terms_in_name = [t for t in name.split() if t not in STOPWORDS]
            df = name_df.get(name) or (dfs.get(terms_in_name[0]) if terms_in_name else None)
            if df is None:
                continue
            for cid in self.by_title.get(name, ()):
                scores[cid] = scores.get(cid, 0.0) + TITLE_BONUS * sim * idf(df, self.n)
        t_score = time.perf_counter()

        top = sorted(scores, key=lambda c: (-scores[c], c))[:k]
        hits = [Hit(c, self.index.chunks[c]["title"], round(scores[c], 3),
                    matched.get(c, {}), self.index.chunks[c]["text"]) for c in top]
        ms = lambda a, b: round((b - a) * 1000, 2)
        return SearchResult(
            question=question, terms=qterms,
            unmatched_terms=[t for t in qterms if not weighted[t][0]],
            names=[f"{n}" if s == 1.0 else f"{n} (sim {s})" for n, s in names],
            hits=hits,
            timings_ms={"total": ms(t0, t_score), "detect_names": ms(t0, t_names),
                        "resolve_variants": ms(t_names, t_resolve), "scoring": ms(t_resolve, t_score)},
            patterns_scanned=len(weighted) + len(phrases), chars_scanned=0, expanded=extra,
            variants={t: [(v.word, v.sim, v.source) for v in vs if v.source != "exact"]
                      for t, (vs, _) in weighted.items()
                      if any(v.source != "exact" for v in vs)},
            chunks_examined=len(scores))


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "What does Blueprnt do?"
    show(ApproxSearcher(Index.load()).search(question))
