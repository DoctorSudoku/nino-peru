#!/usr/bin/env python3
"""
Extrae las cifras de daño de los reportes del INDECI (COEN).

Cada reporte de emergencia enlaza un PDF con la tabla "EVALUACIÓN DE DAÑOS".
Este script descarga (con caché), lee la tabla con PyMuPDF y normaliza las cifras
a un conjunto fijo de métricas.

Requiere: pip install --target .pylibs pymupdf
Uso:     PYTHONPATH=.pylibs python3 scripts/fetch_danos.py
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
CACHE = ROOT / "data" / "raw" / "indeci"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

# métricas normalizadas y sus sinónimos en la tabla
METRICAS = [
    ("personas_damnificadas", ["DAMNIFICAD"]),
    ("personas_afectadas", ["AFECTAD"]),
    ("personas_lesionadas", ["LESIONAD", "HERID"]),
    ("personas_fallecidas", ["FALLECID"]),
    ("personas_desaparecidas", ["DESAPARECID"]),
    ("viviendas_destruidas", ["DESTRUID"]),
    ("viviendas_afectadas", ["AFECTAD"]),
    ("hectareas_cultivo_perdidas", ["CULTIVO", "PERDID"]),
    ("hectareas_cultivo_afectadas", ["CULTIVO", "AFECTAD"]),
    ("hectareas_cobertura_destruida", ["COBERTURA", "DESTRUID"]),
    ("animales_muertos", ["ANIMAL", "MUERT"]),
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.upper())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", "", s)


def get(url: str, tries: int = 3) -> bytes:
    safe = urllib.parse.quote(url, safe=":/?&=%")
    last = None
    for _ in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(safe, headers=UA), timeout=60).read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.2)
    raise RuntimeError(f"No se pudo descargar {url}: {last}")


def numero(cell: str) -> float | None:
    nums = re.findall(r"\d+(?:[.,]\d+)?", cell.replace(" ", ""))
    if not nums:
        return None
    return float(nums[-1].replace(",", "."))


SECCIONES = ("VIDAYSALUD", "VIVIENDA", "PRODUCCION", "COBERTURA", "SERVICIOS",
             "INFRAESTRUCTURA", "AGRICOLA", "PERSONA", "CULTIVO")
NO_SECCION = ("DAMNIFICAD", "AFECTAD", "DESTRUID", "LESIONAD", "FALLECID", "DESAPARECID")


def es_seccion(txt: str) -> bool:
    n = norm(txt)
    return any(k in n for k in SECCIONES) and not any(k in n for k in NO_SECCION)


def clasificar(contexto: str) -> str | None:
    ctx = norm(contexto)
    if "DAMNIFICAD" in ctx:
        return "personas_damnificadas"
    if "FALLECID" in ctx:
        return "personas_fallecidas"
    if "DESAPARECID" in ctx:
        return "personas_desaparecidas"
    if "LESIONAD" in ctx or "HERID" in ctx:
        return "personas_lesionadas"
    if "COBERTURA" in ctx and "DESTRUID" in ctx:
        return "hectareas_cobertura_destruida"
    if "CULTIVO" in ctx and "PERDID" in ctx:
        return "hectareas_cultivo_perdidas"
    if "CULTIVO" in ctx and "AFECTAD" in ctx:
        return "hectareas_cultivo_afectadas"
    if "ANIMAL" in ctx:
        return "animales_muertos" if "MUERT" in ctx else None
    if "VIVIENDA" in ctx and "DESTRUID" in ctx:
        return "viviendas_destruidas"
    if "VIVIENDA" in ctx and "AFECTAD" in ctx:
        return "viviendas_afectadas"
    if ("PERSONA" in ctx or "VIDAYSALUD" in ctx) and "AFECTAD" in ctx:
        return "personas_afectadas"
    return None


def extraer_danos(pdf_path: Path) -> dict:
    """Lee las tablas con 'DAÑOS' y normaliza las cifras por columna.

    Las cabeceras del INDECI combinan celdas: a veces la sección ocupa una celda
    y se extiende varias columnas; a veces todo viene fusionado en una sola celda
    ("VIDAYSALUD (PERSONA) AFECTADA 3"). Se rellena la sección hacia la derecha.
    """
    doc = pymupdf.open(pdf_path)
    metrics: dict[str, float] = {}
    dudosas: dict[str, float] = {}

    for page in doc[:6]:
        for table in page.find_tables().tables:
            rows = table.extract()
            texto = norm(" ".join((c or "") for row in rows for c in row))
            if "DANOS" not in texto and "AFECTACI" not in texto:
                continue
            ncols = max((len(r) for r in rows), default=0)
            seccion = [""] * ncols
            etiquetas = [[] for _ in range(ncols)]
            valores: list[float | None] = [None] * ncols
            bajas: list[tuple[str, float]] = []

            for row in rows:
                actual = ""
                fila_sec = [""] * ncols
                for i in range(ncols):
                    cell_i = (row[i] if i < len(row) else "") or ""
                    if es_seccion(cell_i):
                        actual = norm(cell_i)
                    fila_sec[i] = actual
                for i in range(ncols):
                    cell = (row[i] if i < len(row) else "") or ""
                    if not cell.strip():
                        continue
                    n = norm(cell)
                    if es_seccion(cell):
                        actual = n
                        if not seccion[i]:
                            seccion[i] = n
                    elif re.fullmatch(r"[\d.,]+", n):
                        if valores[i] is None:
                            valores[i] = numero(cell)
                    else:
                        etiquetas[i].append(re.sub(r"[\d.,]", "", n))
                        if re.search(r"\d", n):
                            # celda fusionada. Si tiene una sola cifra es fiable;
                            # con dos o más puede ser una concatenación ("16"+"1"="161").
                            cuantos = re.findall(r"\d+(?:[.,]\d+)?", cell)
                            v = numero(cell)
                            if v is not None:
                                met = clasificar(f"{seccion[i]} {n}")
                                if len(cuantos) == 1 and met:
                                    metrics.setdefault(met, v)
                                else:
                                    bajas.append((f"{seccion[i]} {n}", v))
                # la fila más específica manda: sobrescribe el relleno anterior
                for i in range(ncols):
                    if fila_sec[i]:
                        seccion[i] = fila_sec[i]

            for i in range(ncols):
                ctx = f"{seccion[i]} {' '.join(etiquetas[i])}"
                met = clasificar(ctx)
                if met and valores[i] is not None:
                    metrics.setdefault(met, valores[i])
            for ctx, v in bajas:
                met = clasificar(ctx)
                if met:
                    dudosas.setdefault(met, v)
    # lo dudoso no se publica
    return metrics, dudosas


LIMITES = {
    "personas_damnificadas": 5000, "personas_afectadas": 20000,
    "personas_lesionadas": 500, "personas_fallecidas": 50, "personas_desaparecidas": 100,
    "viviendas_destruidas": 5000, "viviendas_afectadas": 5000,
    "hectareas_cultivo_perdidas": 100000, "hectareas_cultivo_afectadas": 100000,
    "hectareas_cobertura_destruida": 200000, "animales_muertos": 200000,
}


def depurar(metrics: dict) -> tuple[dict, list[str]]:
    """Descarta valores improbables para un evento local y deja rastro del descarte."""
    limpio, descartes = {}, []
    for k, v in metrics.items():
        if v is None:
            continue
        limite = LIMITES.get(k)
        if limite and v > limite:
            descartes.append(f"{k}={v:g} (>{limite})")
            continue
        limpio[k] = v
    return limpio, descartes


def main() -> int:
    inc = json.loads((DATA / "incidencias.json").read_text(encoding="utf-8"))
    CACHE.mkdir(parents=True, exist_ok=True)
    salida, errores = [], []

    for it in inc.get("items", []):
        try:
            slug = re.sub(r"[^a-z0-9]+", "-", it["titulo"].lower())[:80]
            pdf_path = CACHE / f"{slug}.pdf"
            if not pdf_path.exists():
                page = get(it["url"]).decode("utf-8", "ignore")
                m = re.search(r'href="(https://portal\.indeci\.gob\.pe/wp-content/uploads/[^"]+\.pdf)"', page)
                if not m:
                    errores.append(f"sin PDF: {it['titulo'][:60]}")
                    continue
                pdf_path.write_bytes(get(html.unescape(m.group(1))))
                time.sleep(0.5)
            crudas, dudosas = extraer_danos(pdf_path)
            metricas, descartes = depurar(crudas)
            metricas = {k: v for k, v in metricas.items() if k not in dudosas}
            dudosas, descartes_dudosas = depurar(dudosas)
            descartes += descartes_dudosas
            salida.append({
                "titulo": it["titulo"], "tipo": it["tipo"], "departamento": it["departamento"],
                "distrito": it.get("distrito"), "fecha": it.get("fecha"), "url": it["url"],
                "metricas": metricas, "sin_datos": not metricas,
                "dudosas": dudosas or None, "descartes": descartes or None,
            })
        except Exception as exc:  # noqa: BLE001
            errores.append(f"{it['titulo'][:50]}: {exc}")

    # ---- consolidado por departamento (evitando doble conteo de reportes del mismo evento)
    por_evento: dict[tuple, dict] = {}
    for r in salida:
        key = (r["tipo"], r["departamento"], r["distrito"])
        previo = por_evento.get(key)
        # se queda el reporte con más cifras (normalmente el de numeración mayor)
        if previo is None or len(r["metricas"]) > len(previo["metricas"]):
            por_evento[key] = r
    unicos = list(por_evento.values())

    por_dep: dict[str, dict] = {}
    for r in unicos:
        d = por_dep.setdefault(r["departamento"], {
            "departamento": r["departamento"], "eventos": 0,
            "personas_damnificadas": 0, "personas_afectadas": 0,
            "viviendas_destruidas": 0, "viviendas_afectadas": 0,
            "hectareas_cultivo_perdidas": 0, "hectareas_cultivo_afectadas": 0,
            "hectareas_cobertura_destruida": 0,
        })
        d["eventos"] += 1
        for k, v in r["metricas"].items():
            if k in d:
                d[k] += v

    totales = {k: 0 for k in por_dep.get("__none__", {})} if False else {
        "personas_damnificadas": 0, "personas_afectadas": 0,
        "viviendas_destruidas": 0, "viviendas_afectadas": 0,
        "hectareas_cultivo_perdidas": 0, "hectareas_cultivo_afectadas": 0,
        "hectareas_cobertura_destruida": 0,
    }
    for d in por_dep.values():
        for k in totales:
            totales[k] += d[k]

    out = {
        "generated_at": datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat(),
        "fuente": "INDECI — COEN, reportes complementarios (tabla 3.1 Evaluación de daños)",
        "nota": "Los reportes se actualizan con numeración correlativa; se toma el más reciente por evento.",
        "items": salida,
        "por_departamento": sorted(por_dep.values(), key=lambda x: -(x["personas_afectadas"] + x["personas_damnificadas"])),
        "totales": totales,
        "sin_datos": sum(1 for r in salida if r["sin_datos"]),
        "con_dudas": sum(1 for r in salida if r.get("dudosas")),
        "errores": errores,
    }
    (DATA / "danos.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"reportes: {len(salida)} | con cifras: {len(salida) - out['sin_datos']} | sin datos: {out['sin_datos']}")
    for d in out["por_departamento"]:
        print(f"  {d['departamento']:14} ev={d['eventos']} damn={d['personas_damnificadas']:.0f} "
              f"afect={d['personas_afectadas']:.0f} viv.dest={d['viviendas_destruidas']:.0f} "
              f"ha.cult={d['hectareas_cultivo_afectadas']:.0f} ha.cobert={d['hectareas_cobertura_destruida']:.0f}")
    print("totales:", out["totales"])
    if errores:
        print("errores:", errores[:3])
    return 0


if __name__ == "__main__":
    sys.exit(main())
