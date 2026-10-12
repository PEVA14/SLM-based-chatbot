"""Figuras y tablas de la etapa 6 para el reporte (a partir de los JSON medidos).

Entradas : data/stage4_results.json, stage5_results.json, stage6_results.json
Salidas  : docs/figures/*.png  y  docs/etapa6_tablas.md
Uso      : python src/figures.py      (requiere matplotlib: requirements-report.txt)

Paleta: las 3 primeras ranuras categoricas de la paleta de referencia de dataviz,
validadas con validate_palette.js --pairs all. El aguamarina queda bajo 3:1 de
contraste con el fondo, por eso cada serie lleva ademas etiqueta directa y marcador
distinto (alivio exigido por la guia) y las tablas acompanan a las figuras.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA, DOCS = ROOT / "data", ROOT / "docs"
FIG = DOCS / "figures"

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
    "axes.edgecolor": GRID, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "legend.frameon": False,
})


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def fig_scaling(s6):
    rows = s6["scaling"]
    x = [r["corpus_chars"] / 1e6 for r in rows]
    series = [("Exacta, barrido KMP", "exact_kmp_ms", BLUE, "o"),
              ("Aproximada (Trie + trigramas)", "approx_ms", ORANGE, "s"),
              ("Exacta con indice hash", "exact_index_ms", AQUA, "^")]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    for label, key, color, marker in series:
        y = [r[key] for r in rows]
        ax.plot(x, y, color=color, linewidth=2, marker=marker, markersize=8,
                markeredgecolor=SURFACE, markeredgewidth=2, label=label)
        ax.annotate(f"{y[-1]:,.0f} ms", (x[-1], y[-1]), textcoords="offset points",
                    xytext=(8, 0), va="center", color=INK_2, fontsize=9)
    ax.set_yscale("log")
    ax.set_xlabel("Tamano de la coleccion (millones de caracteres)")
    ax.set_ylabel("Tiempo de recuperacion por pregunta (ms, escala log)")
    ax.set_xlim(0, max(x) * 1.18)
    ax.set_title("El barrido crece con la coleccion; el indice casi no")
    ax.legend(loc="upper left", fontsize=9)
    fig.text(0.01, -0.02, "Colecciones de 2x y 4x: fragmentos repetidos (sintetico, solo para tiempo). "
             "Promedio de 8 preguntas representativas.", fontsize=8, color=INK_2)
    fig.tight_layout()
    fig.savefig(FIG / "escalado.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_by_kind(s5):
    names = {"direct": "directa", "synonym": "sinonimo", "no_name": "sin nombre",
             "symbol": "simbolo", "typo": "typo", "inflection": "lista/plural"}
    exact, approx = s5["summary"]["exact"]["by_kind"], s5["summary"]["approx"]["by_kind"]
    kinds = list(names)
    labels = [f"{names[k]}\n(n={approx[k]['n']})" for k in kinds]
    pos = range(len(kinds))
    w = 0.36
    fig, ax = plt.subplots(figsize=(8, 4.4))
    for off, data, color, label in ((-w / 2, exact, BLUE, "Exacta (KMP)"),
                                    (w / 2, approx, ORANGE, "Aproximada")):
        vals = [100 * data[k]["correct"] / data[k]["n"] for k in kinds]
        ax.bar([p + off for p in pos], vals, width=w - 0.04, color=color,
               edgecolor=SURFACE, linewidth=2, label=label)
        for p, v in zip(pos, vals):
            if v == 0:  # una barra de altura 0 es invisible: se rotula para no parecer dato faltante
                ax.text(p + off, 2, "0 %", ha="center", va="bottom", color=INK_2, fontsize=9)
    ax.set_xticks(list(pos))
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Respuestas correctas del modelo (%)")
    ax.set_title("Los typos solo los resuelve la aproximada")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "aciertos_por_tipo.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_context(s6):
    rows = s6["context_selection"]
    labels = [r["config"] for r in rows][::-1]
    vals = [r["correct"] for r in rows][::-1]
    total = rows[0]["answerable"]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    bars = ax.barh(labels, vals, height=0.62, color=BLUE, edgecolor=SURFACE, linewidth=2)
    for bar, v in zip(bars, vals):
        ax.text(v + 0.25, bar.get_y() + bar.get_height() / 2, f"{v}/{total}", va="center",
                color=INK_2, fontsize=9)
    ax.set_xlim(0, total + 2)
    ax.set_xlabel(f"Respuestas correctas de {total} preguntas con respuesta")
    ax.set_title("Si la ficha no cabe no hay respuesta; el ruido resta aciertos")
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(FIG / "seleccion_contexto.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


# ----------------------------------------------------------------------------- tablas
def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def tables(s4, s5, s6):
    e4, a4 = s4["summary"]["exact_kmp_lex"], s4["summary"]["approx"]
    e5, a5 = s5["summary"]["exact"], s5["summary"]["approx"]
    out = ["# Etapa 6: tablas generadas desde los datos medidos",
           "_Generado por `src/figures.py`; no editar a mano._", ""]

    out += ["## 1. Exacta vs aproximada (26 preguntas: 23 con respuesta, 3 sin ella)", "",
            md_table(["Metrica", "Exacta (KMP)", "Aproximada"], [
                ["Tiempo medio de busqueda (ms)", e4["mean_time_ms"], a4["mean_time_ms"]],
                ["Tiempo mediano de busqueda (ms)", e4["median_time_ms"], a4["median_time_ms"]],
                ["Fragmentos examinados (media)", e4["mean_chunks_examined"],
                 a4["mean_chunks_examined"]],
                ["Fragmento con la respuesta en el puesto 1", f"{e4['hit@1']:.0%}", f"{a4['hit@1']:.0%}"],
                ["... entre los 3 primeros", f"{e4['hit@3']:.0%}", f"{a4['hit@3']:.0%}"],
                ["MRR", e4["mrr"], a4["mrr"]],
                ["El contexto elegido contiene la respuesta", f"{e5['context_contains_answer']}/23",
                 f"{a5['context_contains_answer']}/23"],
                ["Respuestas correctas del modelo", f"{e5['correct']}/23", f"{a5['correct']}/23"],
                ["Respuestas erroneas con el contexto correcto presente", e5["wrong_with_support"],
                 a5["wrong_with_support"]],
                ["Abstenciones indebidas", e5["abstained_with_support"] + e5["abstained_no_support"],
                 a5["abstained_with_support"] + a5["abstained_no_support"]],
                ["Abstenciones correctas (sin respuesta en el corpus)",
                 f"{e5['correct_abstention']}/3", f"{a5['correct_abstention']}/3"],
                ["Respuestas inventadas", e5["hallucinated"], a5["hallucinated"]],
                ["Tiempo medio del modelo (ms)", e5["mean_model_ms"], a5["mean_model_ms"]],
                ["Tiempo medio total por pregunta (ms)", e5["mean_total_ms"], a5["mean_total_ms"]],
            ]), ""]

    out += ["## 2. Aislando cada pieza (recuperacion, etapa 4)", "",
            md_table(["Configuracion", "hit@1", "hit@3", "MRR", "Tiempo medio (ms)",
                      "Fragmentos examinados"],
                     [[n, f"{s['hit@1']:.2f}", f"{s['hit@3']:.2f}", s["mrr"], s["mean_time_ms"],
                       s["mean_chunks_examined"]] for n, s in s4["summary"].items()]), ""]

    kinds = list(a5["by_kind"])
    out += ["## 3. Respuestas correctas del modelo por tipo de pregunta", "",
            md_table(["Tipo", "n", "Exacta", "Aproximada"],
                     [[k, a5["by_kind"][k]["n"], e5["by_kind"][k]["correct"],
                       a5["by_kind"][k]["correct"]] for k in kinds]), ""]

    rows = []
    for q, v in s5["per_question"].items():
        e, a = v["exact"], v["approx"]
        er = s4["per_question"][q]["configs"]["exact_kmp_lex"]["answer_rank"]
        ar = s4["per_question"][q]["configs"]["approx"]["answer_rank"]
        if e["outcome"] == a["outcome"] and e["answer"] == a["answer"] and er == ar:
            case = "similar"
        elif e["outcome"] != a["outcome"]:
            case = "DIFERENCIA"
        else:
            case = "similar (distinta posicion)"
        rows.append([case, v["kind"], q, er, ar, e["outcome"], a["outcome"]])
    rows.sort(key=lambda r: (r[0] != "DIFERENCIA", r[1]))
    out += ["## 4. Caso por caso (puesto del fragmento con la respuesta: exacta / aproximada)", "",
            md_table(["Caso", "Tipo", "Pregunta", "Puesto exacta", "Puesto aprox.",
                      "Resultado exacta", "Resultado aprox."], rows), ""]

    out += ["## 5. Escalado con el tamano de la coleccion (ms por pregunta, media de 8)", "",
            md_table(["Escala", "Fragmentos", "Caracteres", "Indice (ms)", "Exacta KMP",
                      "Exacta indice", "Aproximada"],
                     [[f"{r['factor']}x", r["chunks"], f"{r['corpus_chars']:,}",
                       r["index_build_ms"], r["exact_kmp_ms"], r["exact_index_ms"],
                       r["approx_ms"]] for r in s6["scaling"]]), "",
            "_Las escalas 2x y 4x repiten los fragmentos con ids nuevos: son sinteticas._", ""]

    out += ["## 6. Efecto de la seleccion de contexto (recuperacion aproximada fija)", "",
            md_table(["Configuracion", "Correctas", "Erroneas", "Se abstuvo", "Contexto con la respuesta",
                      "Abst. correctas", "Inventadas", "Palabras de contexto", "Modelo (ms)"],
                     [[r["config"], f"{r['correct']}/{r['answerable']}", r["wrong"], r["abstained"],
                       f"{r['context_has_answer']}/{r['answerable']}",
                       f"{r['correct_abstention']}/{r['unanswerable']}", r["hallucinated"],
                       r["mean_context_words"], r["mean_model_ms"]]
                      for r in s6["context_selection"]]), ""]
    return "\n".join(out)


def main():
    s4, s5, s6 = load("stage4_results.json"), load("stage5_results.json"), load("stage6_results.json")
    FIG.mkdir(parents=True, exist_ok=True)
    fig_scaling(s6)
    fig_by_kind(s5)
    fig_context(s6)
    (DOCS / "etapa6_tablas.md").write_text(tables(s4, s5, s6), encoding="utf-8")
    print("figuras ->", FIG, "| tablas ->", DOCS / "etapa6_tablas.md")


if __name__ == "__main__":
    main()
