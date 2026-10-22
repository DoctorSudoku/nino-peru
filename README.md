# El Niño · Perú — tablero de seguimiento

[![Actualizar datos y publicar](https://github.com/USUARIO/nino-peru/actions/workflows/publicar.yml/badge.svg)](https://github.com/USUARIO/nino-peru/actions/workflows/publicar.yml)

Prototipo de tablero periodístico interactivo sobre el fenómeno El Niño-Oscilación Sur
(ENOS), con foco en el Perú (costa peruana, territorios y sectores) y lectura global
(Pacífico central).

Todo dato mostrado es trazable a una fuente oficial y abierta. La página distingue
explícitamente **dato descargado automáticamente** de **dato transcrito a mano desde un
documento oficial con cita de página**.

---

## Cómo verlo

```bash
python3 scripts/build.py          # genera public/data/*.json (no se versionan)
python3 -m http.server -d public 8788
# abrir http://127.0.0.1:8788/
```

Abrir `index.html` con `file://` **no funciona**: el navegador bloquea la lectura de los
JSON por seguridad. Cualquier servidor estático sirve (`npx serve`, `caddy`, GitHub Pages).

## Cómo actualizarlo

```bash
python3 scripts/build.py
```

Descarga las fuentes, reconstruye `public/data/*.json` y guarda un snapshot crudo en
`data/raw/`. No requiere dependencias externas (solo biblioteca estándar de Python 3.10+).

Cuando el ENFEN publica un informe nuevo, hay que actualizar a mano
`data/curated/enfen_state.json` (cifras + cita de página). Esa es la única parte manual,
y es deliberada: el PDF del informe no tiene tablas de datos limpias.

---

## Estructura

```
nino-peru/
├── scripts/
│   ├── build.py                  # pipeline: NOAA + ENFEN + curado → JSON
│   ├── extract_enfen_tables.py   # tablas 4 y 5 del PDF (ríos y embalses) con PyMuPDF
│   ├── fetch_danos.py            # cifras de daño de los PDF del INDECI (PyMuPDF)
│   └── mcp_server.py             # servidor MCP (stdio) sobre los mismos JSON
├── data/
│   ├── curated/enfen_state.json  # cifras oficiales transcritas, con cita de página
│   └── raw/                      # snapshots crudos de cada descarga
├── public/                       # sitio estático (esto es lo que se publica)
│   ├── index.html
│   ├── assets/{app.js,styles.css,echarts.min.js}
│   └── data/{enso,enfen,meta,share}.json
└── docs/
    ├── FUENTES.md                # inventario de fuentes y su estado técnico
    └── PLAN.md                   # hoja de ruta del producto
```

## Páginas

| Archivo | Público | Qué es |
|---|---|---|
| `index.html` | sí | el tablero |
| `glosario.html` | sí | siglas y términos, con buscador |
| `interno/sala-de-redaccion.html` | **no** | textos para redes (fuera de `public/`, no se despliega) |
| `embebibles.html` | sí | gráficos insertables, con código listo para copiar |
| `api.html` | sí | documentación de los endpoints JSON |

> Al desplegar, excluir `sala-de-redaccion.html` y `data/share.json`: son material de
> trabajo, no contenido publicado.

## Interfaz

- **Tema claro y oscuro**, con botón en la barra superior. Respeta la preferencia del
  sistema y la recuerda. Se puede forzar con `?theme=dark`.
- **Mapa de portada**: rejilla real de NOAA (no una imagen), con las cajas Niño 1+2, 3,
  3.4 y 4 dibujadas. Vista Perú o Pacífico completo (`?view=pacifico`).
- Sin dependencias de CDN: ECharts y Leaflet están vendorizados.

## Qué contiene hoy

| Bloque | Contenido | Fuente |
|---|---|---|
| Portada | **Mapa interactivo del mar** (rejilla 0,25°, anomalía y temperatura absoluta, valor al pasar el cursor) | NOAA OISST v2.1 NRT |
| Estado actual | ICEN, ONI, anomalía semanal, próxima actualización | ENFEN + NOAA |
| Cómo se mide | ICEN / RONI / ONI, 13 meses, con umbrales | ENFEN (Tabla 3) |
| Contexto histórico | ONI 1950–2026 y Niño 1+2, con episodios sombreados | NOAA CPC |
| Comparador | Episodios alineados por mes de inicio | NOAA CPC |
| Pronóstico | Magnitud esperada y horizonte temporal | ENFEN (p. 24) |
| Agua y territorio | Ríos (caudal vs. normal), 24 embalses, Titicaca, lluvias en la sierra sur | ENFEN (Tablas 4 y 5) |
| Sectores | Pesca, agricultura, agua/energía, salud | ENFEN + enlaces oficiales |
| Para redes | Tres textos listos para copiar, generados del dato | pipeline |
| Fuentes | Estado de cada feed y metodología | pipeline |

## Dependencia opcional para los daños

Las cifras de daño están dentro de los PDF del INDECI. Para extraerlas:

```bash
python3 -m pip install --target .pylibs pymupdf
python3 scripts/build.py   # detecta .pylibs automáticamente
```

Si PyMuPDF no está instalado, el build sigue funcionando y omite ese bloque.
Los PDFs se cachean en `data/raw/indeci/` para no descargarlos en cada ejecución.

## Servir los datos a otros

- **API**: todos los JSON de `public/data/` son públicos. El catálogo está en
  `public/data/index.json` y la documentación en `api.html`.
- **Embebibles**: `index.html?embed=<sección>` renderiza una sola sección, sin cabecera
  ni pie. `embebibles.html` genera el código `<iframe>` de cada una.
- **MCP**: `python3 scripts/mcp_server.py` expone cuatro herramientas
  (`resumen_actual`, `indices_enso`, `agua_territorio`, `incidencias_recientes`) por
  stdio, para asistentes que hablen Model Context Protocol.

## Publicar y mantener

- [Dónde publicar](docs/DESPLIEGUE.md): GitHub Pages o Cloudflare Pages, ambos gratis,
  y cómo pasar a dominio propio después.
- [Mantenimiento](docs/MANTENIMIENTO.md): rutina diaria, semanal y por informe del ENFEN,
  más el playbook de incidentes.

El despliegue y la actualización de datos corren solos con
`.github/workflows/publicar.yml` (cada 3 horas y a demanda). Verificación previa:

```bash
python3 scripts/build.py && python3 scripts/check_frescura.py
```

La URL pública se configura en `site.config.json`; de ahí salen `robots.txt` y `sitemap.xml`.

## Advertencias metodológicas

- **ICEN ≠ ONI.** ICEN usa Niño 1+2 (costa peruana); ONI usa Niño 3.4. Un mismo evento
  puede ser extraordinario para Perú y moderado globalmente (2017 es el caso de manual).
- **Valores `tmp`** combinan observación con pronóstico NMME; se revisan al informe siguiente.
- **NOAA publica con rezago.** El archivo mensual ERSSTv5 llega a jun-2026; el ONI estacional
  llega a JAS-2026. Por eso el comparador histórico usa ONI.
- **Cobertura parcial.** Agricultura, emergencias y macro siguen en la hoja de ruta
  (`docs/PLAN.md`). El tablero lo dice en pantalla, no lo esconde.

## Licencia y créditos

- **Código**: MIT (ver [LICENSE](LICENSE)).
- **Contenido y datos elaborados**: CC BY 4.0 — se pueden reutilizar citando el tablero.
- **Datos de origen**: NOAA es dominio público; los documentos del ENFEN e INDECI son
  públicos y se citan con su número.

Cita sugerida: *Tablero El Niño Perú. Datos de NOAA CPC, NOAA OISST, Comisión
Multisectorial ENFEN (Informe Técnico Año 12 N° 18, 13 de octubre de 2026) e INDECI.
Consultado en <URL>.* También está en [CITATION.cff](CITATION.cff).

Una iniciativa de **Grupo Evidencia / Media Lamb**.
