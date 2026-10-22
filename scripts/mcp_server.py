#!/usr/bin/env python3
"""
Servidor MCP mínimo (stdio) para el tablero El Niño Perú.

Expone los JSON que genera scripts/build.py como herramientas consultables por
asistentes que hablen Model Context Protocol.

Uso:
    python3 scripts/mcp_server.py

Configuración típica en un cliente MCP:
    { "command": "python3", "args": ["scripts/mcp_server.py"] }

Protocolo: JSON-RPC 2.0, un mensaje por línea (transporte stdio).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"

TOOLS = [
    {
        "name": "resumen_actual",
        "description": "Estado vigente de El Niño en el Perú: alerta del ENFEN, ICEN, ONI, "
                       "anomalía semanal del mar y próxima actualización oficial.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "indices_enso",
        "description": "Serie mensual de índices ENSO de NOAA (Niño 1+2, 3, 3.4, 4 y ONI). "
                       "Permite pedir los últimos N meses o una ventana de años.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ultimos_meses": {"type": "integer", "minimum": 1, "maximum": 900, "default": 24},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "agua_territorio",
        "description": "Caudales de ríos y estado de reservorios según el último informe del ENFEN, "
                       "opcionalmente filtrado por zona (Pacífico Norte, Centro, Sur, Titicaca).",
        "inputSchema": {
            "type": "object",
            "properties": {"zona": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "incidencias_recientes",
        "description": "Reportes de emergencia del INDECI de las últimas horas, agrupados por "
                       "departamento, con tipo de evento y enlace al reporte.",
        "inputSchema": {
            "type": "object",
            "properties": {"departamento": {"type": "string"}},
            "additionalProperties": False,
        },
    },
]


def load(name: str) -> dict:
    path = DATA / name
    if not path.exists():
        raise FileNotFoundError(f"Falta {path}. Ejecute scripts/build.py")
    return json.loads(path.read_text(encoding="utf-8"))


def tool_resumen_actual() -> dict:
    enfen = load("enfen.json")
    enso = load("enso.json")
    semana = (enfen.get("weekly", {}).get("rows") or [{}])[-1]
    ultimo = (enfen.get("indices") or [{}])[-1]
    return {
        "alerta": enfen.get("alert", {}).get("level"),
        "magnitud_proyectada": enfen.get("alert", {}).get("magnitude_forecast"),
        "proximo_comunicado": enfen.get("alert", {}).get("next_update"),
        "icen": {"mes": ultimo.get("month"), "valor": ultimo.get("icen"), "categoria": ultimo.get("icen_cat")},
        "oni": {"temporada": f"{enso.get('oni_latest', {}).get('season')} {enso.get('oni_latest', {}).get('y')}",
                "valor": enso.get("oni_latest", {}).get("anom")},
        "mar_semana": {"fecha": semana.get("date"), "nino_1_2": semana.get("n12a"), "nino_3_4": semana.get("n34a")},
        "pronostico": enfen.get("forecast", []),
        "fuente": "ENFEN Informe Técnico Año 12 N° 18 (13-oct-2026) y NOAA CPC",
    }


def tool_indices_enso(ultimos_meses: int = 24) -> dict:
    enso = load("enso.json")
    meses = enso.get("monthly", [])[-int(ultimos_meses):]
    return {
        "unidad": "°C de anomalía respecto de 1991-2020",
        "n": len(meses),
        "desde": f"{meses[0]['y']}-{meses[0]['m']:02d}" if meses else None,
        "hasta": f"{meses[-1]['y']}-{meses[-1]['m']:02d}" if meses else None,
        "mensual": [{"mes": f"{m['y']}-{m['m']:02d}", "nino12": m["n12a"], "nino3": m["n3a"],
                     "nino34": m["n34a"], "nino4": m["n4a"]} for m in meses],
        "episodios": [{k: e[k] for k in ("start", "end", "peak", "peak_label", "ongoing")}
                      for e in enso.get("oni_episodes", [])],
    }


def tool_agua_territorio(zona: str | None = None) -> dict:
    agua = load("agua.json")
    rios = agua.get("rios", [])
    if zona:
        rios = [r for r in rios if zona.lower() in (r.get("zona") or "").lower()]
    return {
        "rios": [{"rio": r["rio"], "zona": r["zona"], "anomalia_pct": r.get("oct_anom"),
                  "condicion": r.get("oct_cond")} for r in rios],
        "reservorios": [{"nombre": r["reservorio"], "porcentaje_util": r["pct_util"],
                         "departamento": r["departamento"]} for r in agua.get("reservorios", [])],
        "fuente": "ENFEN, Tablas 4 y 5 del Informe Técnico N° 18",
    }


def tool_incidencias(departamento: str | None = None) -> dict:
    inc = load("incidencias.json")
    items = inc.get("items", [])
    if departamento:
        items = [i for i in items if departamento.lower() in i.get("departamento", "").lower()]
    return {
        "total": len(items),
        "items": [{"tipo": i["tipo"], "departamento": i["departamento"], "distrito": i.get("distrito"),
                   "fecha": i.get("fecha"), "url": i["url"]} for i in items[:30]],
        "fuente": "INDECI — COEN",
    }


HANDLERS = {
    "resumen_actual": lambda a: tool_resumen_actual(),
    "indices_enso": lambda a: tool_indices_enso(a.get("ultimos_meses", 24)),
    "agua_territorio": lambda a: tool_agua_territorio(a.get("zona")),
    "incidencias_recientes": lambda a: tool_incidencias(a.get("departamento")),
}


def respond(id_, result=None, error=None) -> dict:
    msg = {"jsonrpc": "2.0", "id": id_}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    return msg


def handle(msg: dict) -> dict | None:
    method = msg.get("method")
    id_ = msg.get("id")

    if method == "initialize":
        return respond(id_, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "nino-peru", "version": "0.1.0"},
        })
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "tools/list":
        return respond(id_, {"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        handler = HANDLERS.get(name)
        if not handler:
            return respond(id_, error={"code": -32602, "message": f"Herramienta desconocida: {name}"})
        try:
            data = handler(args)
            return respond(id_, {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=1)}]})
        except Exception as exc:  # noqa: BLE001
            return respond(id_, error={"code": -32603, "message": str(exc)})
    if id_ is not None:
        return respond(id_, error={"code": -32601, "message": f"Método no soportado: {method}"})
    return None


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        out = handle(msg)
        if out is not None:
            sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
