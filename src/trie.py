"""Etapa 2b: Trie (arbol de prefijos) con frecuencias.

Usos en el proyecto:
  * Autocompletado de la GUI (complete).
  * Vocabulario para corregir typos con Levenshtein acotado (etapa 4).
  * Indice de nombres de cartas.

Complejidad (n palabras, L longitud media, m = |prefijo|):
  insert / get : O(L) tiempo.
  complete     : O(m + S) donde S = tamano del subarbol bajo el prefijo.
  espacio      : O(nodos) <= O(suma de longitudes); los prefijos comunes se comparten.
"""
import heapq


class TrieNode:
    __slots__ = ("children", "count")

    def __init__(self):
        self.children = {}
        self.count = 0  # > 0 solo si una palabra termina aqui (frecuencia)


class Trie:
    def __init__(self):
        self.root = TrieNode()
        self.words = 0   # palabras distintas
        self.nodes = 1   # incluye la raiz

    def insert(self, word, count=1):
        node = self.root
        for ch in word:
            nxt = node.children.get(ch)
            if nxt is None:
                nxt = node.children[ch] = TrieNode()
                self.nodes += 1
            node = nxt
        if node.count == 0:
            self.words += 1
        node.count += count

    def _find(self, prefix):
        node = self.root
        for ch in prefix:
            node = node.children.get(ch)
            if node is None:
                return None
        return node

    def get(self, word):
        """Frecuencia de la palabra (0 si no existe)."""
        node = self._find(word)
        return node.count if node else 0

    def __contains__(self, word):
        return self.get(word) > 0

    def __len__(self):
        return self.words

    def complete(self, prefix, k=5):
        """Hasta k palabras que empiezan con `prefix`, por frecuencia descendente."""
        start = self._find(prefix)
        if start is None:
            return []
        found, stack = [], [(start, prefix)]
        while stack:
            node, path = stack.pop()
            if node.count:
                found.append((path, node.count))
            for ch, child in node.children.items():
                stack.append((child, path + ch))
        return heapq.nsmallest(k, found, key=lambda wc: (-wc[1], wc[0]))

    def fuzzy(self, word, max_dist, fixed_prefix=0):
        """Palabras del Trie a distancia de Levenshtein <= max_dist de `word`.

        Recorre el arbol llevando UNA fila de la tabla de programacion dinamica por
        nodo (fila j = distancia entre el camino actual y word[:j]) y poda la rama
        cuando el minimo de la fila supera max_dist. Los primeros `fixed_prefix`
        caracteres deben coincidir exactamente (los typos casi nunca estan en la
        primera letra, y esto reduce mucho el ruido y el tiempo).

        Devuelve [(palabra, distancia, frecuencia)] ordenado por distancia, frecuencia.
        Tiempo: O(nodos visitados * |word|); la poda lo mantiene muy por debajo de
        recorrer todo el vocabulario (O(V * |word|)).
        """
        node = self._find(word[:fixed_prefix])
        if node is None:
            return []
        rest = word[fixed_prefix:]
        n = len(rest)
        found = []
        first = list(range(n + 1))
        if node.count and n <= max_dist:
            found.append((word[:fixed_prefix], n, node.count))
        stack = [(node, word[:fixed_prefix], first)]
        while stack:
            node, path, prev = stack.pop()
            for ch, child in node.children.items():
                row = [prev[0] + 1]
                for j in range(1, n + 1):
                    row.append(min(prev[j] + 1, row[j - 1] + 1,
                                   prev[j - 1] + (rest[j - 1] != ch)))
                if row[n] <= max_dist and child.count:
                    found.append((path + ch, row[n], child.count))
                if min(row) <= max_dist:
                    stack.append((child, path + ch, row))
        found.sort(key=lambda r: (r[1], -r[2], r[0]))
        return found

    def items(self):
        """Todas las (palabra, frecuencia), en orden alfabetico."""
        out, stack = [], [(self.root, "")]
        while stack:
            node, path = stack.pop()
            if node.count:
                out.append((path, node.count))
            for ch in sorted(node.children, reverse=True):
                stack.append((node.children[ch], path + ch))
        return out
