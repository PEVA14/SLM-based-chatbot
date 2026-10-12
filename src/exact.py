"""Etapa 3a: algoritmos de busqueda exacta de cadenas.

Todos devuelven las posiciones de inicio de *todas* las ocurrencias (incluidas
las traslapadas) de `pattern` en `text`.

  kmp_search    Knuth-Morris-Pratt (funcion de fallo / prefijo).
                Tiempo O(n + m), espacio O(m). Nunca retrocede en `text`.
  z_search      Z-function sobre pattern + sentinela + text.
                Tiempo O(n + m), espacio O(n + m).
  naive_search  Comparacion directa, O(n*m) en el peor caso. Solo sirve como
                referencia de correccion y de tiempo.

n = len(text), m = len(pattern).
"""


def failure_function(pattern):
    """fail[i] = longitud del borde propio mas largo de pattern[:i+1]."""
    fail = [0] * len(pattern)
    k = 0
    for i in range(1, len(pattern)):
        while k and pattern[i] != pattern[k]:
            k = fail[k - 1]
        if pattern[i] == pattern[k]:
            k += 1
        fail[i] = k
    return fail


def kmp_search(text, pattern):
    if not pattern:
        return []
    fail = failure_function(pattern)
    m = len(pattern)
    last = m - 1
    matches, k = [], 0
    for i, ch in enumerate(text):
        while k and ch != pattern[k]:
            k = fail[k - 1]
        if ch == pattern[k]:
            if k == last:
                matches.append(i - last)
                k = fail[k]
            else:
                k += 1
    return matches


def z_function(s):
    """z[i] = longitud del prefijo comun mas largo entre s y s[i:]."""
    n = len(s)
    z = [0] * n
    l = r = 0  # ventana [l, r) = caja Z mas a la derecha
    for i in range(1, n):
        if i < r:
            z[i] = min(r - i, z[i - l])
        while i + z[i] < n and s[z[i]] == s[i + z[i]]:
            z[i] += 1
        if i + z[i] > r:
            l, r = i, i + z[i]
    return z


def z_search(text, pattern, sentinel="\x00"):
    """El sentinela no debe aparecer ni en `pattern` ni en `text`."""
    if not pattern:
        return []
    m = len(pattern)
    z = z_function(pattern + sentinel + text)
    return [i - m - 1 for i in range(m + 1, len(z)) if z[i] == m]


def naive_search(text, pattern):
    m = len(pattern)
    if not m:
        return []
    return [i for i in range(len(text) - m + 1) if text[i:i + m] == pattern]


ALGORITHMS = {"kmp": kmp_search, "z": z_search, "naive": naive_search}
