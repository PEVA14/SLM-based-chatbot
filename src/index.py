"""Etapa 2c: estructuras de indexacion sobre los fragmentos.

Estructuras:
  vocab      Trie de terminos (sin stopwords) con frecuencia global -> autocompletado
             y vocabulario para correccion de typos.
  postings   Tabla hash termino -> {id_fragmento: frecuencia}. Da df/tf para
             puntuar y permite saber cuantos fragmentos contienen un termino.
  names      Trie de nombres de cartas normalizados ("mr bones", "blueprint").
  joined[i]  Texto normalizado del fragmento i (tokens separados por espacio), sobre
             el que corren KMP y Z en la etapa 3.

Complejidad (N = tokens totales, V = vocabulario, P = pares (termino, fragmento)):
  construccion : O(N) tiempo esperado (hash) + O(suma de longitudes) para el Trie.
  espacio      : O(P) para postings + O(nodos del Trie) + O(texto) para joined.
"""
import json
from pathlib import Path

from preprocess import joined as to_joined
from preprocess import terms, tokens
from trie import Trie

CHUNKS_PATH = Path(__file__).resolve().parent.parent / "data" / "chunks.json"


class Index:
    def __init__(self, chunks):
        self.chunks = chunks
        self.joined = []
        self.vocab = Trie()
        self.postings = {}
        self.names = Trie()
        self.title_of = {}  # nombre normalizado -> titulo original ("mr bones" -> "Mr. Bones")
        self.total_tokens = 0
        self.total_terms = 0

        for chunk in chunks:
            toks = tokens(chunk["text"])
            self.joined.append(" ".join(toks))
            self.total_tokens += len(toks)
            for term in terms(chunk["text"]):
                self.total_terms += 1
                self.vocab.insert(term)
                docs = self.postings.setdefault(term, {})
                docs[chunk["id"]] = docs.get(chunk["id"], 0) + 1

        for title in {c["title"] for c in chunks}:
            self.names.insert(to_joined(title))
            self.title_of[to_joined(title)] = title

    @classmethod
    def load(cls, path=CHUNKS_PATH):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def df(self, term):
        """Fragmentos que contienen el termino."""
        return len(self.postings.get(term, ()))

    def vocabulary(self):
        """Palabras unicas del corpus, con su frecuencia, en orden alfabetico."""
        return self.vocab.items()

    def autocomplete(self, prefix, k=5):
        """Sugerencias de palabras (Trie de vocabulario) para un prefijo ya normalizado."""
        return [w for w, _ in self.vocab.complete(prefix, k)]

    def stats(self):
        pairs = sum(len(d) for d in self.postings.values())
        return {
            "chunks": len(self.chunks),
            "tokens": self.total_tokens,
            "terms_without_stopwords": self.total_terms,
            "vocabulary_size": len(self.vocab),
            "trie_nodes": self.vocab.nodes,
            "card_names": len(self.names),
            "posting_pairs": pairs,
            "joined_chars": sum(len(j) for j in self.joined),
        }
