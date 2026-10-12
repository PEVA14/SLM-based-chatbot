"""Formula de puntuacion compartida por la busqueda exacta (etapa 3) y la aproximada (etapa 4).

Usar la misma formula en ambas hace que la comparacion de la etapa 6 mida la
diferencia entre *encontrar coincidencias* exactas o aproximadas, no entre dos
formulas de ranking distintas.
"""
import math

K1, B = 1.2, 0.75


def idf(df, n):
    """Rareza de un patron: ln(1 + (N - df + .5) / (df + .5))."""
    return math.log(1 + (n - df + 0.5) / (df + 0.5))


def tf_saturation(f, length, avg_length):
    """Saturacion BM25: la 10a repeticion aporta mucho menos que la 1a, y los
    fragmentos largos se penalizan un poco."""
    return f * (K1 + 1) / (f + K1 * (1 - B + B * length / avg_length))
