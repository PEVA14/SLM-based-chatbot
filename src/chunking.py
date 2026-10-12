"""Etapa 1b: divide el corpus en fragmentos recuperables.

Criterio:
  * Fragmento 0 de cada pagina = ficha (infobox en frases) + primer parrafo.
    Asi efecto, rareza, costo y desbloqueo viajan juntos.
  * El resto de la prosa se empaqueta en bloques de ~TARGET palabras, cortando
    solo en limites de oracion/linea y con traslape de ~OVERLAP palabras.
  * Todo fragmento lleva el prefijo "<Titulo>:" para que sea autocontenido.

Entrada: data/raw/pages.json      Salida: data/chunks.json, data/corpus_stats.json
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "pages.json"
OUT = ROOT / "data" / "chunks.json"
STATS = ROOT / "data" / "corpus_stats.json"

TARGET = 120   # palabras objetivo por fragmento (sin contar el prefijo)
OVERLAP = 20   # palabras que se repiten entre fragmentos consecutivos
MAX_UNIT = 160  # una unidad (linea) mas larga que esto se parte por oraciones

SINGULAR = {
    "Jokers": "Joker", "Tarot Cards": "Tarot card", "Planet Cards": "Planet card",
    "Spectral Cards": "Spectral card", "Vouchers": "Voucher", "Editions": "Edition",
    "Enhancements": "Enhancement", "Seals": "Seal", "Stickers": "Sticker",
    "Decks": "Deck", "Stakes": "Stake", "Blinds": "Blind", "Tags": "Tag",
    "Rules": "Game rules",
}


def nwords(s):
    return len(s.split())


def infobox_text(title, category, infobox):
    parts = [f"{title} ({SINGULAR.get(category, category)})."]
    for name, value in infobox:
        value = value.rstrip(".")
        if "price" in name.lower() and value.isdigit():
            value = f"${value}"
        parts.append(f"{name}: {value}.")
    return " ".join(parts)


def split_units(prose):
    """Lineas de la prosa; las muy largas se parten por oraciones."""
    units, heading = [], ""
    for line in prose.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("§ "):  # el encabezado se pega a la linea siguiente
            heading = line[2:] + ": "
            continue
        line, heading = heading + line, ""
        if nwords(line) <= MAX_UNIT:
            units.append(line)
        else:
            units += [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"(])", line) if s]
    return units


def pack(units):
    """Empaqueta unidades en bloques ~TARGET palabras con traslape."""
    blocks, cur, cur_w = [], [], 0
    for u in units:
        w = nwords(u)
        if cur and cur_w + w > TARGET:
            blocks.append(cur)
            tail, tw = [], 0
            for prev in reversed(cur):  # traslape: ultimas unidades <= OVERLAP palabras
                if tw + nwords(prev) > OVERLAP:
                    break
                tail.insert(0, prev)
                tw += nwords(prev)
            cur, cur_w = tail, tw
        cur.append(u)
        cur_w += w
    if cur and (not blocks or cur != blocks[-1][-len(cur):]):
        blocks.append(cur)
    return [" ".join(b) for b in blocks]


def build_chunks(pages):
    chunks = []

    def add(page, text):
        chunks.append({"id": len(chunks), "title": page["title"],
                       "category": page["category"], "text": f"{page['title']}: {text}"})

    for page in pages:
        units = split_units(page["prose"])
        if page["category"] != "Rules" and page["infobox"]:
            head = infobox_text(page["title"], page["category"], page["infobox"])
            if units:  # el primer parrafo acompana a la ficha
                head += " " + units.pop(0)
            add(page, head)
        for block in pack(units):
            add(page, block)
    return chunks


def main():
    pages = json.loads(RAW.read_text(encoding="utf-8"))
    chunks = build_chunks(pages)
    OUT.write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")

    all_text = " ".join(c["text"] for c in chunks)
    prose_words = sum(nwords(p["prose"]) for p in pages)
    by_cat = {}
    for p in pages:
        by_cat[p["category"]] = by_cat.get(p["category"], 0) + 1
    sizes = [nwords(c["text"]) for c in chunks]
    stats = {
        "documents": len(pages),
        "documents_by_category": by_cat,
        "prose_words": prose_words,
        "chunk_text_words": nwords(all_text),
        "chunk_text_chars": len(all_text),
        "chunks": len(chunks),
        "chunk_words_avg": round(sum(sizes) / len(sizes), 1),
        "chunk_words_min": min(sizes),
        "chunk_words_max": max(sizes),
        "params": {"target": TARGET, "overlap": OVERLAP},
        "source": "https://balatrowiki.org (CC BY-NC-SA 3.0)",
    }
    STATS.write_text(json.dumps(stats, indent=1), encoding="utf-8")
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
