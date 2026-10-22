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


def _lineas(page, y_min: float, y_max: float) -> list[list]:
    """Agrupa las palabras de una franja vertical en líneas (por línea base)."""
    ws = [w for w in page.get_text("words") if y_min <= w[1] <= y_max]
    ws.sort(key=lambda w: (w[1], w[0]))
    lineas, actual, base = [], [], None
    for w in ws:
        if base is None or abs(w[1] - base) < 3.5:
            actual.append(w)
            base = w[1] if base is None else base
        else:
            lineas.append(sorted(actual, key=lambda x: x[0]))
            actual, base = [w], w[1]
    if actual:
        lineas.append(sorted(actual, key=lambda x: x[0]))
    return lineas


def _ancla_danos(page) -> tuple[float, float] | None:
    """Devuelve la franja y donde vive la tabla de daños de la página."""
    lineas = _lineas(page, 0, page.rect.height)
    ini = fin = None
    for ln in lineas:
        txt = norm(" ".join(w[4] for w in ln))
        if ini is None and re.match(r"^3\.?1", txt):
            ini = ln[0][1]
        elif ini is not None and (txt.startswith("NOTA") or txt.startswith("FUENTE")
                                  or re.match(r"^(3\.2|4\.)", txt)):
            fin = ln[0][1]
            break
    if ini is None:
        return None
    return ini, (fin if fin is not None else min(ini + 200, page.rect.height))


SECCION_PALABRAS = {
    "VIDA", "SALUD", "PERSONA", "VIVIENDA", "COBERTURA", "NATURAL", "CULTIVO",
    "MATERIALES", "SECTORES", "DIVERSOS", "INFRAESTRUCTURA", "SERVICIOS",
    "AGRICOLA", "PECUARIO", "ANIMALES", "ANIMAL",
}
# conectores que forman parte del nombre de la sección ("VIDA Y SALUD")
CONECTORES = {"Y", "DE", "A", "DEL", "LA"}
ETIQUETA_PALABRAS = {
    "DAMNIFICADA", "DAMNIFICADAS", "AFECTADA", "AFECTADAS", "HERIDA", "HERIDAS",
    "LESIONADA", "LESIONADAS", "FALLECIDA", "FALLECIDAS", "DESAPARECIDA",
    "DESAPARECIDAS", "DESTRUIDA", "DESTRUIDAS", "AFECTADO", "PERDIDA", "PERDIDAS",
    "MUERTOS", "MUERTAS", "(HA)",
}


def _mayus(t: str) -> str:
    return norm(t)


def extraer_por_coordenadas(page) -> dict[str, float]:
    """Lee la tabla de daños sin depender de que PyMuPDF detecte una tabla.

    Los reportes del INDECI maquetan la tabla con espacios, sin bordes, así que
    ``find_tables`` no ve nada. Aquí se reconstruye la grilla:

    1. cada etiqueta de columna (DAMNIFICADA, DESTRUIDA…) forma una columna;
    2. cada columna hereda la sección que tiene justo encima (VIDA Y SALUD,
       VIVIENDA, COBERTURA NATURAL…);
    3. cada cifra de la fila DPTO./PROV./DIST. se asigna a la columna que cae
       sobre ella.
    """
    franja = _ancla_danos(page)
    if not franja:
        return {}
    lineas = _lineas(page, *franja)
    if not lineas:
        return {}
    corte = next((ln[0][1] for ln in lineas
                  if _mayus(" ".join(w[4] for w in ln)).startswith(("DPTO", "PROV", "DIST"))), None)
    if corte is None:
        return {}

    cabecera = [w for ln in lineas if ln[0][1] < corte for w in ln]
    cuerpo = [ln for ln in lineas if ln[0][1] >= corte]

    # --- secciones: frases contiguas de la misma línea
    secciones = []
    for ln in lineas:
        if ln[0][1] >= corte:
            break
        grupo = []
        for w in ln:
            pal = _mayus(w[4])
            if pal in SECCION_PALABRAS or (grupo and pal in CONECTORES):
                if grupo and w[0] - grupo[-1][2] > 14:
                    secciones.append(grupo); grupo = []
                grupo.append(w)
            elif grupo:
                secciones.append(grupo); grupo = []
        if grupo:
            secciones.append(grupo)
    secciones = [(g[0][0], g[-1][2], g[0][1], " ".join(w[4] for w in g)) for g in secciones]

    # --- columnas: etiquetas alineadas en vertical
    etiquetas = [w for w in cabecera if _mayus(w[4]) in ETIQUETA_PALABRAS]
    columnas = []  # [x0, x1, y_min, etiquetas]
    for w in sorted(etiquetas, key=lambda x: x[0]):
        centro = (w[0] + w[2]) / 2
        for col in columnas:
            if abs((col[0] + col[1]) / 2 - centro) <= 14:
                col[0] = min(col[0], w[0]); col[1] = max(col[1], w[2])
                col[3].append(w[4])
                break
        else:
            columnas.append([w[0], w[2], w[1], [w[4]]])
    if not columnas:
        return {}

    # --- cada columna hereda la sección más cercana por encima
    def secciones_de(col):
        """Secciones candidatas, de la más cercana hacia arriba."""
        centro = (col[0] + col[1]) / 2
        cand = [(col[2] - y, texto) for x0, x1, y, texto in secciones
                if col[2] - y > 1 and x0 - 30 <= centro <= x1 + 30]
        return [t for _, t in sorted(cand)]

    def nombre_col(col):
        """Sección + etiqueta; si la más cercana no clasifica, se prueba la siguiente."""
        etiqueta = " ".join(col[3])
        for sec in secciones_de(col):
            if clasificar(f"{sec} {etiqueta}"):
                return f"{sec} {etiqueta}"
        cands = secciones_de(col)
        return f"{cands[0] if cands else ''} {etiqueta}"

    # --- cifras del cuerpo
    metricas: dict[str, float] = {}
    for ln in cuerpo:
        for w in ln:
            token = w[4].strip()
            if not re.fullmatch(r"\d+(?:[.,]\d+)?", token):
                continue
            centro = (w[0] + w[2]) / 2
            col = min(columnas, key=lambda c: abs((c[0] + c[1]) / 2 - centro))
            if abs((col[0] + col[1]) / 2 - centro) > 26:
                continue
            met = clasificar(nombre_col(col))
            if met:
                metricas[met] = metricas.get(met, 0) + numero(token)
    return metricas


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

    # Si no hubo tabla detectable, o no aportó cifras, se lee por coordenadas.
    if not metrics:
        for page in doc[:6]:
            for met, v in extraer_por_coordenadas(page).items():
                metrics.setdefault(met, v)

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
