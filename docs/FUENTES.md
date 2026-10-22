# Inventario de fuentes

Estado verificado el **21 de octubre de 2026** desde este equipo. La columna «estado
técnico» es lo que realmente respondió, no lo que la documentación promete.

## Automatizadas (en el pipeline)

| Fuente | Endpoint | Qué aporta | Frecuencia | Estado técnico |
|---|---|---|---|---|
| NOAA CPC — índices Niño | `https://www.cpc.ncep.noaa.gov/data/indices/ersst5.nino.mth.91-20.ascii` | Historia mensual de Niño 1+2, 3, 3.4 y 4 desde 1950 | mensual | ✅ texto plano, sin clave. **Ojo:** el orden de columnas es 1+2, 3, **4, 3.4** (no el habitual). **Suele ir 1–4 meses por detrás** |
| NOAA CPC — índices Niño NRT | `https://www.cpc.ncep.noaa.gov/data/indices/sstoi.indices` | Misma serie mensual, alcanza el último mes cerrado (arranca en 1982) | mensual | ✅ texto plano, mismo formato y orden de columnas. Es la que manda en los meses recientes: el pipeline empalma NRT (1982+) con ERSSTv5 (1950–1981) |
| NOAA CPC — ONI | `https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt` | ONI estacional (media móvil 3 meses, Niño 3.4) | mensual | ✅ texto plano; llega una temporada más adelante que el archivo mensual |
| ENFEN — sitio | `https://enfen.imarpe.gob.pe/` | Lista de informes técnicos y comunicados con fechas | quincenal | ✅ WordPress; los documentos están en `/download/...` (WPDM) |
| ENFEN — REST | `https://enfen.imarpe.gob.pe/wp-json/wp/v2/posts` | Notas de prensa y comunicados con fecha | continuo | ✅ JSON limpio |
| NOAA OISST v2.1 NRT (CoastWatch ERDDAP) | `https://coastwatch.pfeg.noaa.gov/erddap/griddap/ncdcOisst21NrtAgg.csv` | Rejilla 0,25° de TSM y anomalía para el mapa | **diaria** | ✅ CSV por caja geográfica; `last` da el dato más reciente (ayer). Devuelve `NaN` sobre tierra: hay que limpiarlo o el JSON queda inválido |

> El dominio `enfen.gob.pe` **no resuelve** (DNS). El sitio operativo es
> `enfen.imarpe.gob.pe`. Hay páginas antiguas que aún enlazan al dominio muerto.>
> ⚠️ **Desde los servidores de GitHub Actions, `enfen.imarpe.gob.pe` tampoco resuelve**
> (`Temporary failure in name resolution`). El build usa entonces
> `data/curated/enfen_documentos.json`, una copia fechada de los últimos documentos.
> Para refrescarla hay que ejecutar el build desde el Perú y volver a commitear ese
> archivo. La tabla de fuentes lo marca como **"respaldo"**.

## Verificadas a mano (curadas, con cita de página)

| Documento | Qué se extrae | Nota |
|---|---|---|
| Informe Técnico ENFEN Año 12 N° 18 (13 oct 2026), 86 p. | ICEN/RONI/ONI (Tabla 3, p. 26), pronóstico (p. 24), embalses (p. 17), ríos (p. 16), desembarques de anchoveta (p. 15), tabla semanal OISST (Tabla 2, p. 25) | El PDF tiene 17 MB y no ofrece capa de datos limpia: la transcripción es una decisión editorial, no una limitación temporal |

Descarga directa del informe:
`https://enfen.imarpe.gob.pe/download/informe-tecnico-enfen-ano-12-n18-al-13-de-octubre-de-2026-2/?wpdmdl=2166`

## Fuentes para la siguiente fase (probadas y con obstáculo conocido)

| Fuente | Para qué | Estado técnico |
|---|---|---|
| BCRP — API de series | PBI agropecuario y pesquero, inflación de alimentos | ⚠️ HTTP 200 pero devuelve un challenge de **Incapsula** en vez de JSON. Requiere navegador real o proxy con cookies |
| MIDAGRI — SISAP mayorista | Precios mayoristas por producto y mercado | ⚠️ **Certificado SSL vencido**; responde 500. Sirve con `-k` pero no es publicable así |
| MIDAGRI — SIEA | Producción agrícola, superficie, rendimientos | ⏳ portal con descargas por formulario; sin API |
| PRODUCE / IMARPE | Desembarques, cuotas, temporadas de anchoveta | ⏳ `imarpe.gob.pe` responde 403 a clientes automatizados; `repositorio.imarpe.gob.pe` sí responde |
| SENAMHI | Avisos meteorológicos, caudales, estaciones | ⏳ sin API pública documentada; las páginas son portales, no tablas |
| INDECI — feed de emergencias | Reportes del COEN con lugar y tipo de evento | ✅ RSS; cada reporte enlaza un PDF con la tabla de daños |
| INDECI — PDFs de reportes | Damnificados, viviendas, hectáreas por evento | ⚠️ la tabla 3.1 no tiene estructura fija: a veces fusiona dos cifras en una celda ("16"+"1"="161"). Solo se publican celdas con una única cifra; el resto se descarta |
| INDECI / SINPAD (visor) | Emergencias y daños consolidados | ⏳ sin API; el visor geoespacial es público |
| CENEPRED / SIGRID | Escenarios de riesgo por lluvias | ⏳ documentos PDF por evento |
| PRODUCE — datos abiertos | Descargas de anchoveta por puerto, zona y fecha | ✅ CSV de 10 MB (2025) y 2 MB (2026) en datosabiertos.gob.pe |
| Open-Meteo | Pronóstico diario por ciudad | ✅ sin clave; API multi-ciudad en una sola llamada |
| FAO FPMA / FAOSTAT | Precios internacionales de alimentos | ✅ responde; API FAOSTAT abierta |
| Banco Mundial — Pink Sheet | Commodities (incluye fertilizantes y alimentos) | ✅ xlsx abierto |
| NOAA CoastWatch / ERDDAP | Mapas de anomalía de TSM para visualización | ✅ ERDDAP con salida CSV/PNG (en uso) |
| NASA MUR / JPL (`jplMURSST41anom1day`) | Anomalía a 1 km, más detalle costero | ✅ disponible en el mismo ERDDAP |
| NOAA Coral Reef Watch | Anomalía 5 km orientada a blanqueamiento de coral | ✅ por explorar |
| Copernicus/OSTIA | TSM 0,05° europea | ⚠️ requiere clave de API |
| CARTO basemaps | Mapas base claros/oscuros | ❌ desde 2026 exige clave; se usa Esri (Canvas Light/Dark Gray), sin clave |

## Reglas de integridad del proyecto

1. Ninguna cifra sin fuente y fecha de corte.
2. Si un dato es transcripción manual, se marca como tal en la interfaz.
3. Si una fuente falla, la página lo dice en la tabla de estado (no desaparece en silencio).
4. Los valores provisionales se etiquetan (`tmp`).
5. No se comparan índices distintos (ICEN vs ONI) como si fueran lo mismo.
