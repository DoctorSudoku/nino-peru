#!/usr/bin/env python3
"""
Extrae las Tablas 4 (caudales de ríos) y 5 (reservorios) del Informe Técnico ENFEN
y las deja en data/curated/agua_territorio.json.

Requiere PyMuPDF (pip install --target .pylibs pymupdf).
Uso: PYTHONPATH=.pylibs python3 scripts/extract_enfen_tables.py ruta/al/informe.pdf

Por qué existe este script: el informe no publica los datos en formato abierto y la
extracción automática de texto los mezcla. Esto deja rastro de cómo se obtuvieron.
"""

import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "curated" / "agua_territorio.json"

COND = {
    "Significativamente sobre lo normal",
    "Ligeramente sobre lo normal",
    "Normal",
    "Ligeramente por debajo de lo normal",
    "Significativamente por debajo de lo normal",
}
ZONES = {"Pacifico Norte", "Pacifico Centro", "Pacifico Sur", "Titicaca", "Amazonas"}
NUM = re.compile(r"^-?\d+(\.\d+)?$")

# Corrección de nombres partidos por el salto de línea del PDF
NAME_FIX = {
    "Chira (Ardilla_R.Poechos)": "Chira (Ardilla)",
    "Locumba_Pte viejo": "Locumba (Pte. Viejo)",
    "Sama_La Tranca": "Sama (La Tranca)",
    "Sama_Coruca": "Sama (Coruca)",
}


HEADERS = {
    "Zona", "Ríos", "Pentadiarios (m3/s)", "Promedio", "(m3/s)", "Anomalía", "(%)",
    "Condición", "Septiembre 2026", "Octubre 2026", "Tabla 4. Caudales de los principales ríos del país al 10 de octubre del 2026.",
}


def parse_rivers(doc) -> tuple[list[dict], list[str]]:
    """Máquina de estados por fila: nombre → 6-8 números (sep) → condición → 3-5 números (oct) → condición."""
    tokens = []
    for page in (29, 30, 31, 32):
        for line in doc[page].get_text().split("\n"):
            line = line.strip()
            if line:
                tokens.append(line)

    # el PDF parte las condiciones largas en dos líneas ("Ligeramente por debajo de lo" + "normal")
    merged = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok not in COND and tok.startswith(("Ligeramente", "Significativamente")):
            acc, j = tok, i + 1
            while j < len(tokens) and acc not in COND and j <= i + 3:
                acc = f"{acc} {tokens[j]}".strip()
                j += 1
            if acc in COND:
                merged.append(acc)
                i = j
                continue
        merged.append(tok)
        i += 1
    tokens = merged

    rivers, skipped = [], []
    zone, name, buf = None, None, []
    sept, sept_cond = None, None
    state = "name"

    for tok in tokens:
        if tok in HEADERS or tok.startswith("Tabla"):
            continue
        if tok in ZONES:
            zone, state, name, buf, sept = tok, "name", None, [], None
            continue
        is_num = bool(NUM.match(tok.replace(",", "")))

        if state == "name":
            if is_num:
                continue
            name, buf, state = tok, [], "sep"
            continue

        if state == "sep":
            if is_num:
                buf.append(float(tok.replace(",", "")))
            elif tok in COND:
                if 7 <= len(buf) <= 8:
                    sept, sept_cond = buf[-1], tok
                    state = "oct"
                else:
                    skipped.append(f"{name}: sep con {len(buf)} números")
                    state = "name"
                buf = []
            continue

        if state == "oct":
            if is_num:
                buf.append(float(tok.replace(",", "")))
            elif tok in COND:
                if 3 <= len(buf) <= 5:
                    rivers.append({
                        "zona": zone, "rio": NAME_FIX.get(name, name),
                        "sept_anom": sept, "sept_cond": sept_cond,
                        "oct_anom": buf[-1], "oct_cond": tok,
                    })
                else:
                    skipped.append(f"{name}: oct con {len(buf)} números")
                state, name, buf, sept, sept_cond = "name", None, [], None, None
            elif name and buf == []:
                # el río anterior no traía columna de octubre
                skipped.append(f"{name}: sin dato de octubre")
                rivers.append({"zona": zone, "rio": NAME_FIX.get(name, name),
                               "sept_anom": sept, "sept_cond": sept_cond,
                               "oct_anom": None, "oct_cond": None})
                name, buf, sept, sept_cond, state = tok, [], None, None, "sep"
    # descarta filas cuyo "nombre" es en realidad una condición partida
    clean = [r for r in rivers if r["rio"] and not any(r["rio"].startswith(c[:12]) for c in COND)]
    return clean, skipped


def parse_reservoirs(doc) -> list[dict]:
    lines = [l.strip() for l in doc[32].get_text().split("\n")]
    rows, zone = [], None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line in {"Costa - Norte", "Costa - Centro", "Costa - Sur", "Sierra - Centro", "Sierra - Sur"}:
            zone = line
            i += 1
            continue
        # fila: nombre, fecha, departamento, capacidad, almacenado, %
        if (i + 5 < len(lines) and not NUM.match(line) and "SUB TOTAL" not in line
                and line not in {"Zona", "Reservorio", "Fecha", "Reporte"}
                and re.match(r"^\d+-(Oct|Set)$", lines[i + 1] or "")):
            try:
                cap = float(lines[i + 3].replace(",", ""))
                alm = float(lines[i + 4].replace(",", ""))
                pct = float(lines[i + 5].replace(",", ""))
                rows.append({
                    "zona": zone, "reservorio": line, "fecha": lines[i + 1],
                    "departamento": lines[i + 2].strip(),
                    "capacidad_hm3": cap, "almacenado_hm3": alm, "pct_util": pct,
                })
            except ValueError:
                pass
            i += 6
            continue
        i += 1
    return rows


def main() -> int:
    pdf = sys.argv[1] if len(sys.argv) > 1 else "/tmp/enfen_inf.pdf"
    doc = pymupdf.open(pdf)
    rivers, skipped = parse_rivers(doc)
    reservoirs = parse_reservoirs(doc)

    data = {
        "_readme": "Extraído automáticamente de las Tablas 4 y 5 del Informe Técnico ENFEN Año 12 N° 18 "
                   "con scripts/extract_enfen_tables.py. Revisar antes de publicar.",
        "provenance": {
            "document": "Informe Técnico ENFEN, Año 12, N° 18",
            "cutoff": "2026-10-13",
            "tabla_rios": "Tabla 4, pp. 27-32 — caudales al 10 de octubre de 2026",
            "tabla_reservorios": "Tabla 5, p. 33 — reservorios al 12 de octubre de 2026",
        },
        "rios": rivers,
        "reservorios": reservoirs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"ríos: {len(rivers)} | reservorios: {len(reservoirs)} | descartados: {len(skipped)}")
    for s_ in skipped:
        print("   !", s_)
    for r in rivers[:6]:
        print(f"  {r['zona']:15} {r['rio'][:28]:28} sept {r['sept_anom']:>7} oct {r['oct_anom']:>7}  {r['oct_cond']}")
    for r in reservoirs[:4]:
        print(f"  {r['zona']:12} {r['reservorio'][:16]:16} {r['pct_util']:5}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
