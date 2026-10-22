#!/usr/bin/env python3
"""
Pipeline de datos del tablero El Niño Perú.

Fuentes:
  - NOAA CPC  (automático)  : índices Niño mensuales ERSSTv5 + ONI estacional
  - ENFEN     (automático)  : comunicados e informes técnicos (WordPress REST)
  - ENFEN     (curado)      : cifras transcritas del Informe Técnico N° 18, con cita de página

Salida: public/data/{enso,enfen,meta}.json  (+ snapshots crudos en data/raw/)
Uso:   python3 scripts/build.py
"""

from __future__ import annotations

import html
import json
import os
import math
import re
import xml.etree.ElementTree as ET
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "public" / "data"
CURATED = ROOT / "data" / "curated" / "enfen_state.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

SOURCES = {
    "noaa_nino": {
        "name": "NOAA CPC — Índices Niño mensuales (ERSSTv5)",
        "url": "https://www.cpc.ncep.noaa.gov/data/indices/ersst5.nino.mth.91-20.ascii",
        "publisher": "NOAA Climate Prediction Center",
        "frequency": "mensual",
        "license": "Dominio público (gobierno de EE. UU.)",
    },
    "noaa_oni": {
        "name": "NOAA CPC — Oceanic Niño Index (ONI)",
        "url": "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt",
        "publisher": "NOAA Climate Prediction Center",
        "frequency": "mensual",
        "license": "Dominio público (gobierno de EE. UU.)",
    },
    "noaa_sst": {
        "name": "NOAA OISST v2.1 (near-real-time) — rejilla de anomalía",
        "url": "https://coastwatch.pfeg.noaa.gov/erddap/griddap/ncdcOisst21NrtAgg",
        "publisher": "NOAA NCEI / CoastWatch ERDDAP",
        "frequency": "diaria",
        "license": "Dominio público (gobierno de EE. UU.)",
    },
    "indeci": {
        "name": "INDECI — Reportes de emergencia (COEN)",
        "url": "https://portal.indeci.gob.pe/emergencias/feed/",
        "publisher": "Instituto Nacional de Defensa Civil",
        "frequency": "varias veces al día",
        "license": "Documentos públicos; se cita la fuente",
    },
    "prensa": {
        "name": "Prensa peruana — RPP y Agencia Andina (RSS)",
        "url": "https://rpp.pe/rss",
        "publisher": "RPP Noticias · Agencia Andina",
        "frequency": "continua",
        "license": "Titulares con enlace al original",
    },
    "produce": {
        "name": "PRODUCE — Descargas de anchoveta (datos abiertos)",
        "url": "https://www.datosabiertos.gob.pe/dataset/registro-innominado-de-descargas-de-anchoveta-para-consumo-humano-indirecto-ministerio-de-la",
        "publisher": "Ministerio de la Producción (DGSF)",
        "frequency": "trimestral",
        "license": "Open Data Commons Attribution",
    },
    "openmeteo": {
        "name": "Open-Meteo — Pronóstico por ciudad",
        "url": "https://api.open-meteo.com/v1/forecast",
        "publisher": "Open-Meteo (modelos ECMWF, GFS, ICON)",
        "frequency": "diaria",
        "license": "CC BY 4.0 (uso no comercial gratuito)",
    },
    "enfen": {
        "name": "ENFEN — Informes técnicos y comunicados oficiales",
        "url": "https://enfen.imarpe.gob.pe/",
        "publisher": "Comisión Multisectorial ENFEN (IMARPE, SENAMHI, ANA, DIHIDRONAV, IGP, INDECI, CENEPRED)",
        "frequency": "quincenal / mensual",
        "license": "Documentos públicos; se cita la fuente",
    },
}

SEASONS = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]
SEASON_CENTER = dict(zip(SEASONS, range(1, 13)))  # DJF -> enero (mes central)

status: dict[str, dict] = {}


def fetch(url: str, key: str, tries: int = 3, timeout: int = 40) -> bytes:
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            RAW.mkdir(parents=True, exist_ok=True)
            (RAW / f"{key}.raw").write_bytes(data)
            status[key] = {"ok": True, "at": now_iso(), "bytes": len(data)}
            return data
        except Exception as exc:  # noqa: BLE001
            last = exc
    status[key] = {"ok": False, "at": now_iso(), "error": str(last)[:200]}
    raise RuntimeError(f"Fallo al descargar {url}: {last}")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def fnum(s: str) -> float:
    return float(s)


# --------------------------------------------------------------------------- NOAA
def parse_nino(raw: bytes) -> list[dict]:
    rows = []
    for line in raw.decode("utf-8", "ignore").splitlines():
        parts = line.split()
        if len(parts) < 10 or not parts[0].isdigit():
            continue
        y, m = int(parts[0]), int(parts[1])
        vals = [float(x) for x in parts[2:10]]
        # Orden real del archivo CPC: NINO1+2, NINO3, NINO4, NINO3.4
        rows.append(
            {
                "y": y,
                "m": m,
                "n12": vals[0], "n12a": vals[1],
                "n3": vals[2], "n3a": vals[3],
                "n4": vals[4], "n4a": vals[5],
                "n34": vals[6], "n34a": vals[7],
            }
        )
    rows.sort(key=lambda r: (r["y"], r["m"]))
    return rows


def parse_oni(raw: bytes) -> list[dict]:
    rows = []
    for line in raw.decode("utf-8", "ignore").splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[0] not in SEASON_CENTER:
            continue
        try:
            rows.append(
                {"season": parts[0], "y": int(parts[1]), "total": float(parts[2]), "anom": float(parts[3])}
            )
        except ValueError:
            continue
    rows.sort(key=lambda r: (r["y"], SEASON_CENTER[r["season"]]))
    return rows


def month_index(y: int, m: int) -> int:
    return y * 12 + (m - 1)


def detect_episodes(monthly: list[dict], threshold: float = 0.5, min_months: int = 5) -> list[dict]:
    """Episodios de El Niño a partir de la anomalía mensual de Niño 3.4."""
    eps, run = [], []
    for r in monthly:
        if r["n34a"] >= threshold:
            run.append(r)
        else:
            if run:
                eps.append(run)
            run = []
    if run:
        eps.append(run)

    out = []
    last = monthly[-1]
    for run in eps:
        ongoing = run[-1] is last or (run[-1]["y"] == last["y"] and run[-1]["m"] == last["m"])
        if len(run) < min_months and not ongoing:
            continue
        peak = max(run, key=lambda r: r["n34a"])
        out.append(
            {
                "start": f"{run[0]['y']:04d}-{run[0]['m']:02d}",
                "end": f"{run[-1]['y']:04d}-{run[-1]['m']:02d}",
                "months": len(run),
                "peak": round(peak["n34a"], 2),
                "peak_month": f"{peak['y']:04d}-{peak['m']:02d}",
                "ongoing": ongoing,
                "series": [
                    {"t": month_index(r["y"], r["m"]) - month_index(run[0]["y"], run[0]["m"]),
                     "v": round(r["n34a"], 2)}
                    for r in run[:30]
                ],
            }
        )
    return out


def detect_oni_episodes(oni: list[dict], threshold: float = 0.5, min_seasons: int = 5) -> list[dict]:
    """Episodios de El Niño sobre el ONI estacional (media móvil de 3 meses, NOAA)."""
    runs, run = [], []
    for r in oni:
        if r["anom"] >= threshold:
            run.append(r)
        else:
            if run:
                runs.append(run)
            run = []
    if run:
        runs.append(run)

    last = oni[-1]
    out = []
    for run in runs:
        ongoing = run[-1] is last
        if len(run) < min_seasons and not ongoing:
            continue
        peak = max(run, key=lambda r: r["anom"])

        def label(r):
            return f"{r['y']:04d}-{SEASON_CENTER[r['season']]:02d}"

        out.append(
            {
                "id": f"{run[0]['y']}-{run[0]['season']}",
                "start": label(run[0]),
                "end": label(run[-1]),
                "seasons": len(run),
                "peak": round(peak["anom"], 2),
                "peak_label": peak["season"] + " " + str(peak["y"]),
                "peak_year": peak["y"],
                "label": peak["season"] + " " + str(peak["y"]),
                "ongoing": ongoing,
                "series": [
                    {"t": i, "v": round(r["anom"], 2), "label": r["season"] + " " + str(r["y"])}
                    for i, r in enumerate(run)
                ],
            }
        )
    return out


def build_enso(nino_raw: bytes, oni_raw: bytes) -> dict:
    monthly = parse_nino(nino_raw)
    oni = parse_oni(oni_raw)
    episodes = detect_episodes(monthly)
    current = next((e for e in episodes if e["ongoing"]), None)
    oni_episodes = detect_oni_episodes(oni)
    oni_current = next((e for e in oni_episodes if e["ongoing"]), None)

    # Percentil simple del último valor frente a la climatología de la serie
    hist = sorted(r["n34a"] for r in monthly[:-1])
    last_val = monthly[-1]["n34a"]
    pct = round(100 * sum(1 for v in hist if v <= last_val) / len(hist), 1)

    return {
        "generated_at": now_iso(),
        "dataset_note": (
            "Anomalías de TSM respecto de la climatología 1991–2020 (ERSSTv5, NOAA CPC). "
            "El ONI es la media móvil de 3 meses de la anomalía en Niño 3.4, asignada al mes central. "
            "El ICEN peruano usa la misma metodología sobre Niño 1+2: no es idéntico al ONI."
        ),
        "latest_month": monthly[-1],
        "monthly": monthly,
        "oni": oni,
        "episodes": episodes,
        "current_episode": current,
        "oni_episodes": oni_episodes,
        "oni_current": oni_current,
        "oni_latest": oni[-1],
        "lag_note": (
            f"El archivo mensual ERSSTv5 de NOAA llega hasta {monthly[-1]['y']}-{monthly[-1]['m']:02d}; "
            "el ONI estacional llega una temporada más adelante. Por eso el comparador histórico usa ONI."
        ),
        "stats": {
            "n_months": len(monthly),
            "first_month": f"{monthly[0]['y']:04d}-{monthly[0]['m']:02d}",
            "last_n34a_percentile": pct,
            "last_n12a_percentile": round(
                100 * sum(1 for r in monthly[:-1] if r["n12a"] <= monthly[-1]["n12a"]) / len(monthly[:-1]), 1
            ),
        },
    }


# ---------------------------------------------------------------------------- SST
SST_FUENTES = [
    ("https://coastwatch.pfeg.noaa.gov/erddap/griddap/ncdcOisst21NrtAgg.csv", "NOAA OISST v2.1 NRT (0,25°)"),
    ("https://www.ncei.noaa.gov/erddap/griddap/ncdc_oisst_v2_avhrr_by_time_zlev_lat_lon.csv",
     "NOAA OISST v2 (0,25°, producto final)"),
]
SST_BASE = SST_FUENTES[0][0]


def sst_query(var: str, lat0: float, lat1: float, lon0: float, lon1: float, stride: float) -> tuple[str, list]:
    """Descarga una caja de la rejilla OISST y la devuelve como array plano."""
    step = max(1, int(round(stride / 0.25)))
    url = (
        f"{SST_BASE}?{var}%5B(last)%5D%5B(0.0):1:(0.0)%5D"
        f"%5B({lat0}):{step}:({lat1})%5D%5B({lon0}):{step}:({lon1})%5D"
    )
    raw, usado = None, None
    for base, etiqueta in SST_FUENTES:
        try:
            raw = fetch(url.replace(SST_BASE, base), f"sst_{var}_{abs(lat0):.0f}_{abs(lon0):.0f}",
                        tries=1, timeout=15).decode("utf-8", "ignore")
            usado = etiqueta
            break
        except Exception:  # noqa: BLE001
            continue
    if raw is None:
        raise RuntimeError("ningún servidor ERDDAP respondió")
    SST_USADA[0] = usado
    lines = [l for l in raw.splitlines() if l and not l.startswith("UTC") and not l.startswith("time")]
    vals, date = [], None
    for line in lines:
        parts = line.split(",")
        if len(parts) < 5:
            continue
        date = date or parts[0]
        try:
            val = float(parts[4])
        except ValueError:
            vals.append(None)
            continue
        # NaN no es JSON válido: se guarda como null
        vals.append(round(val, 1) if math.isfinite(val) else None)
    return date, vals


SST_USADA: list = [None]


def build_sst() -> dict:
    out = {"generated_at": now_iso(), "source": "NOAA OISST vía ERDDAP", "unit": "°C", "boxes": {}}

    specs = {
        "peru": {"lat": (-20, 6), "lon": (265, 290), "step": 0.25, "vars": ("anom", "sst")},
        "pacifico": {"lat": (-20, 20), "lon": (120, 290), "step": 0.5, "vars": ("anom",)},
    }

    for key, sp in specs.items():
        box = {
            "lat0": sp["lat"][0], "lat1": sp["lat"][1],
            "lon0": sp["lon"][0], "lon1": sp["lon"][1],
            "step": sp["step"],
            "nlat": len(range(int(sp["lat"][0]), int(sp["lat"][1]) + 1, int(round(sp["step"] / 0.25)))) if sp["step"] < 0.25 else 1,
        }
        for var in sp["vars"]:
            date, vals = sst_query(var, sp["lat"][0], sp["lat"][1], sp["lon"][0], sp["lon"][1], sp["step"])
            box[var] = vals
            box["date"] = date
        # dimensiones reales a partir del número de valores
        if box.get("anom"):
            nlon = int(round((sp["lon"][1] - sp["lon"][0]) / sp["step"])) + 1
            box["nlon"] = nlon
            box["nlat"] = len(box["anom"]) // nlon
        out["boxes"][key] = box

    d = next((b.get("date") for b in out["boxes"].values() if b.get("date")), None)
    out["date"] = d[:10] if d else None
    out["source"] = SST_USADA[0] or out["source"]
    return out


# -------------------------------------------------------------------------- ENFEN
REPORT_SLUG = re.compile(r"informe-tecnico-enfen-ano-(\d+)-n(\d+)-al-(\d+)-de-([a-z]+)-de-(\d{4})", re.I)
MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "setiembre": 9, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&#8211;", "–").replace("&#8212;", "—").replace("&#8217;", "’")
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#8230;", "…")
    return re.sub(r"\s+", " ", s).strip()


def build_enfen() -> dict:
    posts_raw = fetch(
        "https://enfen.imarpe.gob.pe/wp-json/wp/v2/posts?per_page=20&_fields=date,link,title,excerpt",
        "enfen_posts",
    )
    posts = json.loads(posts_raw)
    news = [
        {
            "date": p["date"][:10],
            "title": strip_html(p["title"]["rendered"]),
            "url": p["link"],
            "summary": strip_html(p["excerpt"]["rendered"])[:400],
        }
        for p in posts
    ]

    home = fetch("https://enfen.imarpe.gob.pe/", "enfen_home").decode("utf-8", "ignore")

    reports: dict[tuple[int, int], dict] = {}
    comunicados: dict[tuple[int, int], dict] = {}
    notas: dict[tuple[int, int], dict] = {}

    for m in re.finditer(r'href="(https://enfen\.imarpe\.gob\.pe/download/[^"]+)"', home):
        url = m.group(1).replace("&amp;", "&")
        slug = urllib.parse.unquote(url.split("?")[0])

        rm = REPORT_SLUG.search(slug.replace("/", " "))
        if rm:
            ano, n, day, month_name, year = rm.groups()
            reports[(int(year), int(n))] = {
                "type": "informe",
                "n": int(n),
                "year": int(year),
                "anio_comision": int(ano),
                "cutoff": f"{int(year):04d}-{MONTHS_ES.get(month_name.lower(), 0):02d}-{int(day):02d}",
                "title": f"Informe Técnico ENFEN Año {ano} N° {n} — corte {int(day)} de {month_name} de {year}",
                "url": url,
            }
            continue

        cm = re.search(r"comunicado-oficial-enfen-n-(\d+)-(\d{4})", slug)
        if cm:
            n, year = int(cm.group(1)), int(cm.group(2))
            # el listado del home trae "peso | 16 Octubre, 2026" junto a cada enlace
            around = home[m.start():m.start() + 1600]
            dm = re.search(r"(\d{1,2})\s+([A-Za-zÁÉÍÓÚáéíóú]+),\s*(\d{4})", around)
            cutoff = None
            if dm:
                day, mname, yr = dm.groups()
                mm = MONTHS_ES.get(mname.lower().rstrip("."), 0)
                if mm:
                    cutoff = f"{int(yr):04d}-{mm:02d}-{int(day):02d}"
            km = re.search(r"([\d.]+)\s*(KB|MB)", around)
            comunicados[(year, n)] = {
                "type": "comunicado",
                "n": n,
                "year": year,
                "cutoff": cutoff,
                "weight": f"{km.group(1)} {km.group(2)}" if km else None,
                "title": f"Comunicado Oficial ENFEN N° {n}-{year}",
                "url": url,
            }
            continue

        nm = re.search(r"nota-tecnica-enfen-(\d+)-(\d{4})", slug)
        if nm:
            n, year = int(nm.group(1)), int(nm.group(2))
            notas[(year, n)] = {
                "type": "nota",
                "n": n,
                "year": year,
                "cutoff": None,
                "title": f"Nota Técnica ENFEN N° {n}-{year}",
                "url": url,
            }

    def _sorted(d):
        return sorted(d.values(), key=lambda r: (r["year"], r["n"]), reverse=True)

    latest = _sorted(reports)[0] if reports else None
    if latest:
        # enriquece el título con la etiqueta del bloque "Último informe técnico"
        lbl = re.search(r"Informe T[eé]cnico ENFEN Año (\d+) N[°º](\d+) al (\d+) de ([a-z]+) de (\d{4})", home)
        if lbl:
            latest["title"] = (
                f"Informe Técnico ENFEN Año {lbl.group(1)} N° {lbl.group(2)} — "
                f"corte {lbl.group(3)} de {lbl.group(4)} de {lbl.group(5)}"
            )

    comunicado_latest = _sorted(comunicados)[0] if comunicados else None

    return {
        "news": news,
        "reports": _sorted(reports),
        "comunicados": _sorted(comunicados)[:12],
        "notas": _sorted(notas)[:6],
        "latest_report": latest,
        "latest_comunicado": comunicado_latest,
    }

# ----------------------------------------------------------------------- PESCA
PESCA_URLS = [
    "https://www.datosabiertos.gob.pe/sites/default/files/DescargaAnchoveta_2025.csv",
    "https://www.datosabiertos.gob.pe/sites/default/files/DescargaAnchoveta_2026_hTrim2.csv",
]


def build_pesca() -> dict:
    """Descargas de anchoveta por puerto, zona y fecha (PRODUCE, datos abiertos)."""
    import collections

    filas = []
    for url in PESCA_URLS:
        nombre = url.rsplit("/", 1)[-1]
        try:
            raw = fetch(url, f"pesca_{nombre[:20]}")
        except Exception:  # noqa: BLE001
            continue
        texto = raw.decode("utf-8", "ignore")
        lineas = [l for l in texto.splitlines() if l.strip()]
        if not lineas:
            continue
        cab = lineas[0].split("|")
        for linea in lineas[1:]:
            partes = linea.split("|")
            if len(partes) < len(cab):
                continue
            d = dict(zip(cab, partes))
            try:
                tm = float(d.get("TMDESCARGADA") or 0)
                fecha = d.get("FECHA_DESCARGA") or ""
                if len(fecha) < 8:
                    continue
                mes = f"{fecha[:4]}-{fecha[4:6]}"
            except ValueError:
                continue
            filas.append({
                "mes": mes, "zona": (d.get("ZONA") or "").strip(),
                "puerto": (d.get("PUERTO") or "").strip(),
                "regimen": "Artesanal" if "26920" in (d.get("REGIMEN") or "") else "Industrial",
                "temporada": (d.get("TEMPORADA") or "").strip(),
                "tm": tm,
            })

    if not filas:
        raise RuntimeError("sin datos de PRODUCE")

    meses = collections.defaultdict(lambda: {"total": 0.0, "Norte-Centro": 0.0, "Sur": 0.0})
    puertos = collections.defaultdict(float)
    regimen = collections.defaultdict(float)
    temporadas = collections.defaultdict(float)
    for f in filas:
        m = meses[f["mes"]]
        m["total"] += f["tm"]
        if f["zona"] in ("Norte-Centro", "Sur"):
            m[f["zona"]] += f["tm"]
        puertos[f["puerto"]] += f["tm"]
        regimen[f["regimen"]] += f["tm"]
        if f["temporada"]:
            temporadas[f["temporada"]] += f["tm"]

    serie = [{"mes": k, **{a: round(b, 1) for a, b in v.items()}}
             for k, v in sorted(meses.items())][-18:]

    return {
        "generated_at": now_iso(),
        "fuente": "PRODUCE — Registro de descargas de anchoveta (datos abiertos, DGSF)",
        "unidad": "toneladas métricas",
        "registros": len(filas),
        "cobertura": {"desde": serie[0]["mes"] if serie else None, "hasta": serie[-1]["mes"] if serie else None},
        "mensual": serie,
        "puertos": [{"puerto": k, "tm": round(v, 1)} for k, v in sorted(puertos.items(), key=lambda x: -x[1])[:8]],
        "regimen": [{"nombre": k, "tm": round(v, 1)} for k, v in sorted(regimen.items(), key=lambda x: -x[1])],
        "temporadas": [{"temporada": k, "tm": round(v, 1)} for k, v in sorted(temporadas.items())],
    }


# ------------------------------------------------------------------ PRONÓSTICO
CIUDADES = [
    ("Lima", -12.0464, -77.0428), ("Piura", -5.1945, -80.6328),
    ("Chiclayo", -6.7714, -79.8409), ("Ica", -14.0678, -75.7286),
    ("Iquitos", -3.7491, -73.2538), ("Arequipa", -16.4090, -71.5375),
    ("Cusco", -13.5319, -71.9675),
]


def build_pronostico() -> dict:
    lats = ",".join(str(c[1]) for c in CIUDADES)
    lons = ",".join(str(c[2]) for c in CIUDADES)
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lats}&longitude={lons}"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max"
        "&timezone=America%2FLima&forecast_days=5"
    )
    raw = fetch(url, "openmeteo")
    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]

    ciudades = []
    for (nombre, _lat, _lon), d in zip(CIUDADES, data):
        daily = d.get("daily", {})
        dias = []
        for i, fecha in enumerate(daily.get("time", [])):
            dias.append({
                "fecha": fecha,
                "tmax": daily["temperature_2m_max"][i],
                "tmin": daily["temperature_2m_min"][i],
                "lluvia": daily["precipitation_sum"][i],
                "prob": daily["precipitation_probability_max"][i],
            })
        ciudades.append({"ciudad": nombre, "dias": dias})

    return {
        "generated_at": now_iso(),
        "fuente": "Open-Meteo (ECMWF/GFS/ICON) — no es un pronóstico oficial del SENAMHI",
        "ciudades": ciudades,
    }


# ------------------------------------------------------------------ INCIDENCIAS
DEPARTAMENTOS = {
    "AMAZONAS": (-6.23, -77.87), "ANCASH": (-9.53, -77.53), "APURIMAC": (-13.63, -72.88),
    "AREQUIPA": (-16.40, -71.54), "AYACUCHO": (-13.16, -74.22), "CAJAMARCA": (-6.49, -78.47),
    "CALLAO": (-12.06, -77.15), "CUSCO": (-13.53, -71.97), "HUANCAVELICA": (-12.79, -74.97),
    "HUANUCO": (-9.93, -76.24), "ICA": (-14.07, -75.73), "JUNIN": (-11.16, -75.99),
    "LA LIBERTAD": (-8.11, -78.99), "LAMBAYEQUE": (-6.77, -79.84), "LIMA": (-12.05, -77.04),
    "LORETO": (-4.0, -75.0), "MADRE DE DIOS": (-12.6, -70.0), "MOQUEGUA": (-17.19, -70.93),
    "PASCO": (-10.69, -76.26), "PIURA": (-5.19, -80.63), "PUNO": (-15.84, -70.02),
    "SAN MARTIN": (-6.48, -76.38), "TACNA": (-17.58, -70.24), "TUMBES": (-3.57, -80.45),
    "UCAYALI": (-9.0, -74.0),
}

DEPTO_DISPLAY = {
    "AMAZONAS": "Amazonas", "ANCASH": "Áncash", "APURIMAC": "Apurímac", "AREQUIPA": "Arequipa",
    "AYACUCHO": "Ayacucho", "CAJAMARCA": "Cajamarca", "CALLAO": "Callao", "CUSCO": "Cusco",
    "HUANCAVELICA": "Huancavelica", "HUANUCO": "Huánuco", "ICA": "Ica", "JUNIN": "Junín",
    "LA LIBERTAD": "La Libertad", "LAMBAYEQUE": "Lambayeque", "LIMA": "Lima", "LORETO": "Loreto",
    "MADRE DE DIOS": "Madre de Dios", "MOQUEGUA": "Moquegua", "PASCO": "Pasco", "PIURA": "Piura",
    "PUNO": "Puno", "SAN MARTIN": "San Martín", "TACNA": "Tacna", "TUMBES": "Tumbes",
    "UCAYALI": "Ucayali",
}

TIPOS = [
    ("Lluvias", ["LLUVIAS INTENSAS", "PRECIPITACIONES", "INUNDACION", "DESBORDE", "LLUVIA"]),
    ("Movimiento de tierra", ["HUAICO", "DESLIZAMIENTO", "DERRUMBE", "ALUVION", "REPTACION"]),
    ("Incendio forestal", ["INCENDIO FORESTAL"]),
    ("Vientos", ["VIENTOS FUERTES", "VIENTO", "TORMENTA"]),
    ("Frío", ["HELADA", "FRIAJE", "FRIO", "NEVADA"]),
    ("Sequía", ["SEQUIA", "DEFICIT HIDRICO", "ESTIAJE"]),
    ("Granizo", ["GRANIZADA", "GRANIZO"]),
]


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", s.upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def build_incidencias() -> dict:
    raw = fetch("https://portal.indeci.gob.pe/emergencias/feed/", "indeci_feed")
    root = ET.fromstring(raw)
    items, vistos = [], set()
    for it in root.findall(".//item"):
        title = html.unescape(it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        date = (it.findtext("pubDate") or "").strip()
        ntitle = _norm(title)

        tipo = next((t for t, kws in TIPOS if any(k in ntitle for k in kws)), None)
        if not tipo:
            continue
        dept = next((d for d in DEPARTAMENTOS if d in ntitle), None)
        if not dept:
            continue

        distrito = None
        m = re.search(r"DISTRITO DE ([A-ZÁÉÍÓÚÑ ]+?)(?:\s*[-–]|\s*$)", title, re.I)
        if m:
            distrito = m.group(1).strip().title()

        key = (tipo, dept, ntitle[:60])
        if key in vistos:
            continue
        vistos.add(key)

        lat, lon = DEPARTAMENTOS[dept]
        items.append({
            "tipo": tipo, "departamento": DEPTO_DISPLAY.get(dept, dept.title()), "distrito": distrito,
            "lat": lat, "lon": lon, "titulo": title, "url": link, "fecha": date,
        })
        if len(items) >= 60:
            break

    # conteo por departamento para el mapa
    resumen: dict[str, dict] = {}
    for it in items:
        k = it["departamento"]
        r = resumen.setdefault(k, {"departamento": k, "lat": it["lat"], "lon": it["lon"],
                                   "total": 0, "tipos": {}, "ultimo": it})
        r["total"] += 1
        r["tipos"][it["tipo"]] = r["tipos"].get(it["tipo"], 0) + 1

    return {"generated_at": now_iso(), "items": items,
            "departamentos": sorted(resumen.values(), key=lambda x: -x["total"]),
            "fuente": "INDECI — COEN, reportes de emergencia"}


# --------------------------------------------------------------------- NOTICIAS
FEN_FUERTE = ["EL NIÑO", "FENOMENO EL NIÑO", "ENFEN", "FEN ", "SENAMHI", "COEN", "INDECI"]
FEN_MEDIO = ["LLUVIAS", "HUAICO", "INUNDACION", "DESBORDE", "SEQUIA", "INCENDIO FORESTAL",
             "HELADA", "FRIAJE", "OLA DE CALOR", "DESLIZAMIENTO", "GRANIZADA"]
FEN_ZONA = ["PIURA", "TUMBES", "LAMBAYEQUE", "LA LIBERTAD", "ANCASH", "LIMA", "PUNO", "CUSCO",
            "AMAZONAS", "SAN MARTIN", "LORETO", "UCAYALI", "CAJAMARCA"]

FEEDS_PRENSA = [
    ("RPP Noticias", "https://rpp.pe/rss"),
    ("Agencia Andina", "https://andina.pe/agencia/rss.aspx"),
]


def build_noticias() -> dict:
    noticias = []
    for medio, url in FEEDS_PRENSA:
        try:
            raw = fetch(url, f"rss_{medio.split()[0].lower()}")
            root = ET.fromstring(raw)
        except Exception:  # noqa: BLE001
            continue
        for it in root.findall(".//item"):
            title = html.unescape(re.sub(r"<[^>]+>", "", it.findtext("title") or "")).strip()
            link = (it.findtext("link") or "").strip()
            date = (it.findtext("pubDate") or "").strip()
            if not title or not link:
                continue
            n = _norm(title)
            score = sum(3 for k in FEN_FUERTE if k in n) + sum(2 for k in FEN_MEDIO if k in n) \
                + sum(1 for k in FEN_ZONA if k in n)
            if score >= 2:
                noticias.append({"titulo": title, "url": link, "medio": medio, "fecha": date, "score": score})

    # dedupe, una por medio y luego relleno por relevancia
    vistos, unicas = set(), []
    for n in sorted(noticias, key=lambda x: -x["score"]):
        k = n["titulo"][:70].lower()
        if k in vistos:
            continue
        vistos.add(k)
        unicas.append(n)

    seleccion, medios = [], set()
    for n in unicas:
        if n["medio"] not in medios:
            seleccion.append(n)
            medios.add(n["medio"])
    for n in unicas:
        if len(seleccion) >= 3:
            break
        if n not in seleccion:
            seleccion.append(n)

    return {"generated_at": now_iso(), "items": seleccion[:3], "total_candidatas": len(unicas)}


# --------------------------------------------------------------------------- main
def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []

    try:
        enso = build_enso(
            fetch(SOURCES["noaa_nino"]["url"], "noaa_nino"),
            fetch(SOURCES["noaa_oni"]["url"], "noaa_oni"),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR NOAA: {exc}", file=sys.stderr)
        errors.append(f"NOAA: {exc}")
        enso = {"generated_at": now_iso(), "error": str(exc)}

    try:
        enfen_live = build_enfen()
        status["enfen"] = {"ok": True, "at": now_iso(), "bytes": status.get("enfen_home", {}).get("bytes")}
    except Exception as exc:  # noqa: BLE001
        status["enfen"] = {"ok": False, "at": now_iso(), "error": str(exc)[:200]}
        print(f"ERROR ENFEN: {exc}", file=sys.stderr)
        errors.append(f"ENFEN: {exc}")
        enfen_live = {"news": [], "reports": [], "latest_report": None}

    try:
        sst = build_sst()
        status["noaa_sst"] = {"ok": True, "at": now_iso(), "bytes": 136000}
        (OUT / "sst.json").write_text(
            json.dumps(sst, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8"
        )
        print(f"OK  sst: dato del {sst.get('date')}, cajas " + ", ".join(f"{k}={len(v.get('anom') or [])}" for k, v in sst["boxes"].items()))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR SST: {exc}", file=sys.stderr)
        errors.append(f"SST: {exc}")

    for nombre, fn in (("incidencias", build_incidencias), ("noticias", build_noticias),
                       ("pesca", build_pesca), ("pronostico", build_pronostico)):
        try:
            data = fn()
            clave = {"pesca": "mensual", "pronostico": "ciudades"}.get(nombre, "items")
            contenido = data.get(clave) or []
            if not contenido:
                raise RuntimeError("respuesta vacía")
            status[{"incidencias": "indeci", "noticias": "prensa", "pesca": "produce",
                    "pronostico": "openmeteo"}.get(nombre, nombre)] = {
                "ok": True, "at": now_iso(), "bytes": None}
            (OUT / f"{nombre}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            print(f"OK  {nombre}: {len(contenido)} elementos")
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR {nombre}: {exc}", file=sys.stderr)
            errors.append(f"{nombre}: {exc}")

    # --- cifras de daño: requiere PyMuPDF (pip install --target .pylibs pymupdf)
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT / ".pylibs"))
        import fetch_danos  # noqa: E402
        fetch_danos.main()
    except Exception as exc:  # noqa: BLE001
        print(f"AVISO daños: {exc}", file=_sys.stderr)

    curated = json.loads(CURATED.read_text(encoding="utf-8"))

    # datos hidrológicos extraídos de las tablas 4 y 5 del informe
    agua_src = ROOT / "data" / "curated" / "agua_territorio.json"
    if agua_src.exists():
        agua = json.loads(agua_src.read_text(encoding="utf-8"))
        agua.update({k: curated[k] for k in ("territory",) if k in curated})
        (OUT / "agua.json").write_text(json.dumps(agua, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"OK  agua: {len(agua.get('rios', []))} ríos, {len(agua.get('reservorios', []))} reservorios")
    enfen = {"generated_at": now_iso(), **enfen_live, **{k: v for k, v in curated.items() if not k.startswith("_")}}

    # --- snippets para redes, generados a partir de los datos
    snips = []
    MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "setiembre", "octubre", "noviembre", "diciembre"]

    def d2(v):
        return f"{v:+.2f}".replace(".", ",")

    def d1(v):
        return f"{v:+.1f}".replace(".", ",")

    def mes_largo(iso):
        y, m = iso.split("-")[:2]
        return f"{MESES[int(m) - 1]} de {y}"

    def fecha_larga(iso):
        y, m, d = iso.split("-")[:3]
        return f"{int(d)} de {MESES[int(m) - 1]} de {y}"

    try:
        idx = {r["month"]: r for r in curated["indices"]}
        sep = idx.get("2026-09")
        last = enso["latest_month"]
        semana = (curated.get("weekly", {}).get("rows") or [{}])[-1]

        if sep:
            snips.append(
                f"El Niño costero alcanzó magnitud extraordinaria frente al Perú: el ICEN de "
                f"{mes_largo(sep['month'])} fue de {d2(sep['icen'])} °C, la categoría más alta de la "
                f"escala del ENFEN. El ONI global está en {d2(sep['oni'])} °C "
                f"({sep['oni_cat'].lower()})."
            )
        if semana.get("date"):
            snips.append(
                f"El mar frente a la costa peruana está {d1(semana['n12a']).replace('+', '')} °C por encima "
                f"de lo normal (semana del {fecha_larga(semana['date'])}, OISST). En el Pacífico central la anomalía es "
                f"de {d1(semana['n34a'])} °C. El ENFEN mantiene la alerta de El Niño costero."
            )
        ce = enso.get("oni_current") or enso.get("current_episode")
        if ce:
            snips.append(
                f"El episodio de El Niño en el Pacífico central lleva {ce['seasons'] if 'seasons' in ce else ce['months']} "
                f"temporadas y un pico de {d2(ce['peak'])} °C. En el tablero puedes compararlo mes a mes con "
                f"1982-83, 1997-98 y 2015-16."
            )
    except Exception:  # noqa: BLE001
        pass

    # --- robots y sitemap según el dominio configurado
    cfg_path = ROOT / "site.config.json"
    base = os.environ.get("SITE_URL", "")
    if not base:
        if cfg_path.exists():
            base = json.loads(cfg_path.read_text(encoding="utf-8")).get("url", "")
        base = base or "https://USUARIO.github.io/nino-peru"
    base = base.rstrip("/")

    (OUT.parent / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\nSitemap: " + base + "/sitemap.xml\n", encoding="utf-8"
    )
    paginas = [("", "1.0", "hourly"), ("glosario.html", "0.6", "monthly"),
               ("embebibles.html", "0.5", "monthly"), ("api.html", "0.5", "monthly")]
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for ruta, prio, freq in paginas:
        xml.append(f"  <url><loc>{base}/{ruta}</loc><changefreq>{freq}</changefreq><priority>{prio}</priority></url>")
    xml.append("</urlset>")
    (OUT.parent / "sitemap.xml").write_text("\n".join(xml) + "\n", encoding="utf-8")

    catalogo = {
        "generated_at": now_iso(),
        "licencia": "Datos de NOAA en dominio publico; documentos del ENFEN e INDECI citando la fuente.",
        "endpoints": [
            {"file": "enso.json", "name": "Indices ENSO", "desc": "Serie mensual de NOAA (Nino 1+2, 3, 3.4, 4), ONI estacional y episodios detectados.", "campos": ["monthly[]", "oni[]", "oni_episodes[]", "oni_current", "stats"]},
            {"file": "enfen.json", "name": "ENFEN", "desc": "Alerta vigente, indices mensuales oficiales, pronostico, comunicados e informes.", "campos": ["alert", "indices[]", "forecast[]", "comunicados[]", "reports[]", "sectors[]"]},
            {"file": "sst.json", "name": "Mapa de temperatura del mar", "desc": "Rejilla OISST 0,25 grados (Peru) y 0,5 (Pacifico) de anomalia y temperatura absoluta.", "campos": ["date", "boxes.peru", "boxes.pacifico"]},
            {"file": "agua.json", "name": "Agua y territorio", "desc": "Caudales por rio y estado de los reservorios (Tablas 4 y 5 del informe ENFEN).", "campos": ["rios[]", "reservorios[]", "territory"]},
            {"file": "incidencias.json", "name": "Incidencias", "desc": "Reportes de emergencia del INDECI con departamento, tipo y enlace.", "campos": ["items[]", "departamentos[]"]},
            {"file": "noticias.json", "name": "Noticias", "desc": "Tres titulares de prensa peruana relacionados con el fenomeno.", "campos": ["items[]"]},
            {"file": "pesca.json", "name": "Pesca", "desc": "Descargas de anchoveta por mes, zona, puerto y regimen (PRODUCE).", "campos": ["mensual[]", "puertos[]", "regimen[]", "temporadas[]"]},
            {"file": "pronostico.json", "name": "Pronostico por ciudad", "desc": "Cinco dias de temperatura y lluvia para siete ciudades (Open-Meteo).", "campos": ["ciudades[].dias[]"]},
            {"file": "danos.json", "name": "Danos", "desc": "Damnificados, viviendas y hectareas por departamento (PDF del INDECI).", "campos": ["items[]", "por_departamento[]", "totales"]},
            {"file": "meta.json", "name": "Estado del pipeline", "desc": "Que fuentes respondieron en la ultima ejecucion y cuando.", "campos": ["built_at", "sources[]", "errors[]"]},
        ],
    }
    (OUT / "index.json").write_text(json.dumps(catalogo, ensure_ascii=False, indent=1), encoding="utf-8")

    meta = {
        "built_at": now_iso(),
        "sources": [
            {**SOURCES[k], "id": k, "status": status.get(k, {"ok": False, "error": "no ejecutado"})}
            for k in SOURCES
        ],
        "curated": {
            "id": "enfen_curated",
            "name": "ENFEN — cifras transcritas del Informe Técnico N° 18",
            "document": curated["provenance"]["citation"],
            "cutoff": curated["provenance"]["cutoff"],
            "url": curated["provenance"]["url"],
            "status": {"ok": True, "at": curated["provenance"]["published"]},
        },
        "errors": errors,
    }

    # solo se escribe si la descarga trajo datos: un fallo de red no debe borrar lo anterior
    if enso.get("monthly"):
        (OUT / "enso.json").write_text(json.dumps(enso, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    else:
        print("AVISO: NOAA no respondió; se conserva enso.json anterior", file=sys.stderr)

    if not enfen.get("reports"):
        previo = OUT / "enfen.json"
        if previo.exists():
            viejo = json.loads(previo.read_text(encoding="utf-8"))
            for k in ("reports", "comunicados", "news", "notas", "latest_report", "latest_comunicado"):
                if not enfen.get(k) and viejo.get(k):
                    enfen[k] = viejo[k]
            print("AVISO: ENFEN no respondió; se reutilizan los documentos anteriores", file=sys.stderr)
    (OUT / "enfen.json").write_text(json.dumps(enfen, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "share.json").write_text(json.dumps({"generated_at": now_iso(), "snippets": snips}, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"OK  enso: {enso.get('stats', {}).get('n_months', 0)} meses, "
          f"{len(enso.get('episodes', []))} episodios")
    print(f"OK  enfen: {len(enfen.get('reports', []))} informes, {len(enfen.get('news', []))} notas, "
          f"último informe: {(enfen.get('latest_report') or {}).get('title')}")
    print(f"OK  curado: {len(curated['indices'])} meses de índices, {len(curated['sectors'])} sectores")
    if errors:
        print("ADVERTENCIA:", "; ".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
