#!/usr/bin/env python3
"""
Verifica que los datos publicados estén frescos.

Se ejecuta en CI antes de desplegar. Falla (exit 1) solo si el pipeline no corrió:
un desfase de una fuente se reporta como advertencia, no bloquea la publicación.

Uso: python3 scripts/check_frescura.py [--max-horas 12]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"

# (archivo, campo de fecha, horas máximas tolerables, descripción)
CONTROLES = [
    ("meta.json", "built_at", 12, "última ejecución del pipeline"),
    ("enso.json", "generated_at", 72, "índices de NOAA"),
    ("enfen.json", "generated_at", 72, "ENFEN"),
    ("incidencias.json", "generated_at", 12, "INDECI"),
    ("noticias.json", "generated_at", 12, "prensa"),
    ("pesca.json", "generated_at", 24 * 40, "PRODUCE (trimestral)"),
    ("pronostico.json", "generated_at", 24, "Open-Meteo"),
]


def parse(iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    max_horas = 12
    if "--max-horas" in sys.argv:
        max_horas = int(sys.argv[sys.argv.index("--max-horas") + 1])

    ahora = datetime.now(timezone.utc)
    fallos, avisos = [], []
    print(f"{'archivo':18} {'estado':10} antigüedad")
    print("-" * 52)

    for archivo, campo, limite, desc in CONTROLES:
        ruta = DATA / archivo
        if not ruta.exists():
            fallos.append(f"falta {archivo}")
            print(f"{archivo:18} {'FALTA':10} —")
            continue
        try:
            data = json.loads(ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            fallos.append(f"{archivo} no es JSON válido")
            print(f"{archivo:18} {'CORRUPTO':10} —")
            continue

        valor = data.get(campo)
        fecha = parse(valor) if isinstance(valor, str) else None
        if not fecha:
            avisos.append(f"{archivo} sin {campo}")
            print(f"{archivo:18} {'SIN FECHA':10} —")
            continue

        horas = (ahora - fecha).total_seconds() / 3600
        estado = "OK" if horas <= limite else "VIEJO"
        print(f"{archivo:18} {estado:10} {horas:6.1f} h ({desc})")
        if horas > limite:
            if archivo == "meta.json" and horas > max_horas:
                fallos.append(f"el pipeline no corre desde hace {horas:.0f} h")
            else:
                avisos.append(f"{archivo} tiene {horas:.0f} h (límite {limite})")

    # Vigencia del DATO, no solo del pipeline: un JSON regenerado hace minutos puede contener
    # una serie de hace meses. Pasó en octubre de 2026: la serie mensual publicada era de
    # junio mientras NOAA ya tenía septiembre, y el chequeo anterior no lo veía.
    enso_ruta = DATA / "enso.json"
    if enso_ruta.exists():
        e = json.loads(enso_ruta.read_text(encoding="utf-8"))
        lm = e.get("latest_month") or {}
        cov = e.get("coverage") or {}
        usado = f"{int(lm['y']):04d}-{int(lm['m']):02d}" if lm.get("y") and lm.get("m") else None
        nrt = cov.get("nrt_last")
        print(f"\nserie mensual: publicado {usado or '—'} · fuente NRT {nrt or '—'} · "
              f"ERSSTv5 {cov.get('ersst5_last') or '—'}")
        if usado:
            meses = (ahora.year - int(lm["y"])) * 12 + (ahora.month - int(lm["m"]))
            if meses >= 3:
                fallos.append(f"la serie mensual está {meses} meses atrás ({usado})")
            elif meses >= 2:
                avisos.append(f"la serie mensual va {meses} meses atrás ({usado})")
        if nrt and usado and nrt > usado:
            fallos.append(f"la fuente ya publicó {nrt} y el sitio sirve {usado}")

    # cifras de daño: se informa cobertura, no se exige
    danos = DATA / "danos.json"
    if danos.exists():
        d = json.loads(danos.read_text(encoding="utf-8"))
        print(f"\ndaños: {len(d.get('items', []))} reportes, "
              f"{d.get('sin_datos', 0)} sin cifras utilizables")

    print()
    if avisos:
        print("Advertencias:")
        for a in avisos:
            print(f"  · {a}")
    if fallos:
        print("Errores:")
        for f in fallos:
            print(f"  · {f}")
        return 1
    print("Datos frescos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
