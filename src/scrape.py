"""Etapa 1a: descarga el contexto desde la Balatro Wiki (MediaWiki API).

Fuente: https://balatrowiki.org  (licencia CC BY-NC-SA 3.0, uso academico no comercial).
Salida: data/raw/pages.json  ->  [{title, category, infobox: [[campo, valor], ...], prose}]
"""
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

API = "https://balatrowiki.org/api.php"
HEADERS = {"User-Agent": "TEC-student-project/1.0 (educational, non-commercial)"}
DELAY = 0.25  # segundos entre peticiones

CATEGORIES = [
    "Jokers", "Tarot Cards", "Planet Cards", "Spectral Cards", "Vouchers",
    "Editions", "Enhancements", "Seals", "Stickers", "Decks", "Stakes",
    "Blinds", "Tags",
]
# Paginas generales (reglas del juego) que no pertenecen a una categoria de items.
EXTRA_PAGES = [
    "Poker Hands", "Booster Packs", "Playing Cards", "Shop", "Ante",
    "Card Ranks", "Card Suits", "Challenges", "Rerolls", "Interest",
]
# Secciones de ruido que no aportan al contexto.
DROP_SECTIONS = {"update history", "in other languages", "gallery", "references",
                 "see also", "external links", "contents"}

HEADING = "§ "  # marca de encabezado de seccion dentro de la prosa

OUT = Path(__file__).resolve().parent.parent / "data" / "raw" / "pages.json"


def api(**params):
    params["format"] = "json"
    for attempt in range(4):
        try:
            r = requests.get(API, params=params, headers=HEADERS, timeout=30)
            r.raise_for_status()
            time.sleep(DELAY)
            return r.json()
        except requests.RequestException as e:
            print(f"  retry {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("API no disponible")


def category_members(cat):
    titles, cont = [], {}
    while True:
        d = api(action="query", list="categorymembers", cmtitle=f"Category:{cat}",
                cmlimit=500, cmtype="page", **cont)
        titles += [m["title"] for m in d["query"]["categorymembers"]]
        if "continue" not in d:
            return titles
        cont = d["continue"]


def clean_text(t):
    t = t.replace(" ", " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s+([,.;:)])", r"\1", t)
    t = re.sub(r"\(\s+", "(", t)
    return t.strip()


def parse_infobox(title):
    """Devuelve la lista [(campo, valor)] del infobox, o [] si la pagina no tiene."""
    d = api(action="parse", page=title, prop="text", disablelimitreport=1)
    if "parse" not in d:
        return []
    soup = BeautifulSoup(d["parse"]["text"]["*"], "lxml")
    for t in soup(["style", "script", "img"]):
        t.decompose()
    box = soup.find("div", class_="infobox-root")
    if not box:
        return []
    for t in box.select(".metadata, .noexcerpt, .noprint"):  # datos ocultos de tooltips
        t.decompose()
    for br in box.find_all("br"):
        br.replace_with(", ")
    fields, seen, header = [], set(), None
    for el in box.find_all("div", class_=["infobox-header", "infobox-row-container"]):
        classes = el.get("class", [])
        if "infobox-header" in classes:
            header = clean_text(el.get_text(" "))
            continue
        label = el.find("div", class_="infobox-row-label")
        value = el.find("div", class_="infobox-row-value")
        if not value:
            continue
        name = clean_text(label.get_text(" ")) if label else header
        val = clean_text(value.get_text(" ")).replace("✓ ", "")
        if name and val and (name, val) not in seen:
            seen.add((name, val))
            fields.append((name, val))
    return fields


def fetch_prose(title):
    d = api(action="query", prop="extracts", explaintext=1, titles=title, redirects=1)
    page = next(iter(d["query"]["pages"].values()))
    text = page.get("extract", "")
    out, keep = [], True
    for line in text.split("\n"):
        m = re.match(r"^=+\s*(.*?)\s*=+$", line.strip())
        if m:  # encabezado de seccion
            keep = m.group(1).lower() not in DROP_SECTIONS
            if keep:
                out.append(HEADING + m.group(1))
            continue
        if keep and line.strip():
            out.append(clean_text(line))
    return "\n".join(out)


def main():
    plan = {}  # title -> category (la primera categoria gana)
    for cat in CATEGORIES:
        members = category_members(cat)
        print(f"{cat}: {len(members)} paginas")
        for t in members:
            if t.lower() == cat.lower():  # pagina "hub" de la categoria
                continue
            plan.setdefault(t, cat)
    for t in EXTRA_PAGES:
        plan.setdefault(t, "Rules")

    pages = []
    for i, (title, cat) in enumerate(plan.items(), 1):
        prose = fetch_prose(title)
        if not prose:
            print(f"  [skip] {title}: sin texto")
            continue
        pages.append({"title": title, "category": cat,
                      "infobox": parse_infobox(title), "prose": prose})
        if i % 25 == 0:
            print(f"  {i}/{len(plan)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pages, ensure_ascii=False, indent=1), encoding="utf-8")
    words = sum(len(p["prose"].split()) for p in pages)
    print(f"Guardadas {len(pages)} paginas, ~{words} palabras de prosa -> {OUT}")


if __name__ == "__main__":
    main()
