"""Etapa 4a: primitivas de similitud aproximada entre cadenas.

  levenshtein      Distancia de edicion (insertar, borrar, sustituir), O(|a|*|b|)
                   tiempo y O(min(|a|,|b|)) espacio. Es la referencia con la que se
                   valida Trie.fuzzy, que calcula la misma distancia con poda.
  similarity       1 - d / max(|a|, |b|)  ->  1.0 identicas, 0.0 nada en comun.
  trigrams         Conjunto de trigramas de caracteres de una palabra con bordes
                   ("mult" -> {"_mu","mul","ult","lt_"}).
  jaccard          |A n B| / |A u B| sobre dos conjuntos.
  NgramIndex       Tabla hash trigrama -> palabras del vocabulario. Genera candidatos
                   contando trigramas compartidos (sin comparar contra todo el
                   vocabulario) y los confirma con Jaccard.
"""


def levenshtein(a, b):
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            row.append(min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = row
    return prev[-1]


def similarity(a, b):
    longest = max(len(a), len(b))
    return 1.0 if longest == 0 else 1 - levenshtein(a, b) / longest


def trigrams(word, n=3):
    padded = f"_{word}_"
    if len(padded) < n:
        return {padded}
    return {padded[i:i + n] for i in range(len(padded) - n + 1)}


def jaccard(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


class NgramIndex:
    """Indice de trigramas del vocabulario.

    Construccion: O(suma de longitudes). Consulta: O(sum de |bucket| para cada
    trigrama de la palabra), que es mucho menor que recorrer las V palabras.
    """

    def __init__(self, words):
        self.grams = {}   # palabra -> conjunto de trigramas
        self.buckets = {}  # trigrama -> palabras
        for w in words:
            g = trigrams(w)
            self.grams[w] = g
            for t in g:
                self.buckets.setdefault(t, []).append(w)

    def similar(self, word, threshold=0.4, first_char=True):
        """[(palabra, jaccard)] con Jaccard de trigramas >= threshold, de mayor a menor."""
        query = trigrams(word)
        shared = {}
        for t in query:
            for w in self.buckets.get(t, ()):
                shared[w] = shared.get(w, 0) + 1
        out = []
        for w, inter in shared.items():
            if first_char and w[0] != word[0]:
                continue
            # |A u B| = |A| + |B| - |A n B|: Jaccard sin construir la union.
            score = inter / (len(query) + len(self.grams[w]) - inter)
            if score >= threshold and w != word:
                out.append((w, score))
        out.sort(key=lambda r: (-r[1], r[0]))
        return out
