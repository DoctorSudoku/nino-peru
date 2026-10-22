# API

Todos los datos del tablero son archivos JSON estáticos servidos junto al sitio.
Sin clave, sin registro y con CORS abierto en el despliegue.

Catálogo: `public/data/index.json`.

| Archivo | Contenido | Cadencia |
|---|---|---|
| `enso.json` | Índices Niño mensuales (NOAA), ONI estacional, episodios detectados | diaria |
| `enfen.json` | Alerta, índices oficiales, pronóstico, comunicados e informes | quincenal |
| `sst.json` | Rejilla OISST 0,25° (Perú) y 0,5° (Pacífico) de anomalía y TSM | diaria |
| `agua.json` | Caudales por río y reservorios (Tablas 4 y 5 del informe ENFEN) | quincenal |
| `incidencias.json` | Reportes de emergencia del INDECI con departamento y enlace | continua |
| `noticias.json` | Tres titulares de prensa relacionados con el fenómeno | continua |
| `meta.json` | Estado de cada fuente en la última ejecución | por build |

## Convenciones

- Unidades en °C para temperatura y anomalías; % para caudales y embalses.
- Ausencia de dato = `null`, nunca `0`.
- `generated_at` en ISO 8601 con zona horaria de Lima.
- Los valores `*_tmp` son estimaciones en tiempo real y se revisan al informe siguiente.

## MCP

```bash
python3 scripts/mcp_server.py
```

Herramientas: `resumen_actual`, `indices_enso`, `agua_territorio`, `incidencias_recientes`.
Transporte stdio, JSON-RPC 2.0, un mensaje por línea.
