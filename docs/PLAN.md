# Hoja de ruta

## Principio de diseño

El tablero tiene que resistir la pregunta «¿de dónde sale este número?» en menos de diez
segundos. Por eso la arquitectura separa tres capas:

1. **Automatizada** — se descarga y transforma sola (NOAA, documentos del ENFEN).
2. **Curada** — se transcribe a mano desde un PDF oficial, con documento y página. Es
   lenta pero obliga a leer la fuente.
3. **Derivada** — se calcula sobre las anteriores (percentiles, comparación de episodios,
   textos para redes).

Cada capa se puede reemplazar sin tocar las otras. Cuando una fuente consiga API, el dato
curado se retira y sube a la capa 1.

---

## Estado: v0.6 — hecho

- [x] Descargas mensuales de anchoveta por zona (PRODUCE, datos abiertos)
- [x] Pronóstico de 5 días para Lima, Piura, Chiclayo, Ica, Iquitos, Arequipa y Cusco
- [x] Mapa de incidencias reubicado bajo el comunicado del ENFEN
- [x] Rótulos «Niño 1+2 (costero)» y «Niño 3.4 (global)»
- [x] El build ya no sobrescribe datos buenos cuando falla la red
- [x] Respaldo de ERDDAP (CoastWatch → NCEI) para el mapa del mar

## Pendiente conocido

- El extractor de daños del INDECI falla con las tablas fusionadas: hoy solo 3 de
  10 reportes dejan cifras publicables. Siguiente paso: leer la tabla por coordenadas
  (x/y de cada palabra) en vez de confiar en la detección de líneas del PDF.

## Estado: v0.5 — hecho

- [x] Cifras de daño del INDECI extraídas de los PDF (damnificados, viviendas, hectáreas)
- [x] Consolidado por departamento, con aviso de cobertura (cuántos reportes traen EDAN)
- [x] Daños visibles en la lista de reportes y en una tabla propia

## Estado: v0.4 — hecho

- [x] Etiqueta «beta» en la cabecera y crédito institucional al pie
- [x] Noticias del día (RPP y Andina) con enlace, filtradas por relación con el FEN
- [x] Mapa de incidencias del INDECI por departamento, con lista de reportes
- [x] Panel de agro y pesca (cuota de anchoveta, agua para riego)
- [x] Embebibles por sección con código para copiar
- [x] API documentada + catálogo `data/index.json`
- [x] Servidor MCP con cuatro herramientas

## Estado: v0.3 — hecho

- [x] Glosario en página aparte, con buscador y 40 términos
- [x] "Para redes" fuera del sitio público (pasa a `sala-de-redaccion.html`, no indexada)
- [x] Agua y territorio en cuatro bloques: ríos, embalses, Titicaca, lluvias en la sierra sur
- [x] Extracción reproducible de las Tablas 4 y 5 del informe (51 ríos, 24 embalses)
- [x] Títulos del comparativo corregidos

## Estado: v0.2 (prototipo con mapa e interfaz dual) — hecho

- [x] Mapa interactivo de temperatura del mar (rejilla NOAA OISST 0,25°, diaria)
- [x] Tema claro y oscuro con preferencia persistente
- [x] Cajas Niño 1+2 / 3 / 3.4 / 4 dibujadas sobre el mapa
- [x] Vista Perú y vista Pacífico completo
- [x] Banda de comunicados del ENFEN en portada
- [x] Textos recortados en toda la página

## Estado: v0.1 (prototipo funcional) — hecho

- [x] Pipeline NOAA (índices mensuales + ONI) con snapshots crudos
- [x] Detección automática de episodios y comparador alineado por mes de inicio
- [x] Scraping del ENFEN (informes, comunicados, notas) con fechas
- [x] Capa curada con cita de página para cifras del Informe Técnico N° 18
- [x] Tablero responsive, accesible, con exportación CSV y textos para redes
- [x] Tabla de estado de fuentes (distingue automático / curado / fallo)

## Fase 1 — Completar la capa Perú (2–3 semanas de trabajo)

Prioridad por valor periodístico, no por facilidad técnica.

| # | Objetivo | Fuente | Bloqueo |
|---|---|---|---|
| 1 | Serie de caudales por cuenca (la Tabla 4 del informe) | ENFEN / SENAMHI / ANA | PDF sin datos limpios; hay que transcribir o pedir la data |
| 2 | Desembarques de anchoveta por temporada y cuota | PRODUCE (R.M.) / IMARPE | sin API; publicaciones por resolución |
| 3 | Producción agrícola y precios mayoristas por región | MIDAGRI SIEA + SISAP | SSL vencido en SISAP; SIEA sin API |
| 4 | PBI agropecuario/pesquero e inflación de alimentos | BCRP API | Incapsula bloquea clientes automatizados |
| 5 | Emergencias y daños (Damnificados, hectáreas, viviendas) | INDECI / SINPAD | por explorar |
| 6 | Puntos críticos y escenarios de riesgo | CENEPRED / SIGRID | PDFs por evento |

**Entregable de la fase:** un panel «Impacto» con dos gráficos (agro y pesca) y un mapa de
puntos críticos. Eso convierte el tablero en algo que un editor puede usar en portada.

## Fase 2 — Escala global

- Comparación de El Niño costero peruano con el ciclo global (ya está la base con ONI).
- Precios internacionales de alimentos (FAO FPMA) y commodities (Banco Mundial).
- Teleconexiones documentadas por la propia NOAA/IRI, con enlace a la fuente.
- Mapa de anomalías de TSM (ERDDAP) en lugar de solo series.

## Fase 3 — Producto editorial

- **Alertas por correo/Telegram** cuando el ENFEN publique un comunicado o cuando el ICEN
  cruce un umbral. Se puede resolver con GitHub Actions + cron.
- **Versionado de datos**: guardar cada snapshot y poder decir «el ICEN de setiembre se
  revisó de 4,15 a X en el informe de octubre». Eso es lo que nadie más tiene.
- **Ficha descargable** (PDF/PNG) por episodio, para públicos y redes.
- **Embebibles**: un `<iframe>` por gráfico para que otros medios lo citen.

## Fase 4 — Operación

- Despliegue estático (Cloudflare Pages / Netlify / GitHub Pages) con build automático.
- Repositorio público, con el `data/raw` versionado para auditoría.
- Revisión editorial quincenal: alguien firma cada actualización curada.
- SEO y accesibilidad: datos estructurados, textos alternativos, contraste AA.

---

## Decisiones pendientes

1. **Identidad editorial.** ¿Es un producto de un medio, de una organización, o neutral?
   Cambia el tono, la marca y la política de correcciones.
2. **Frecuencia comprometida.** El ENFEN publica cada dos semanas; NOAA semanal-mensual.
   ¿Se actualiza a mano en cada comunicado o se automatiza con cron?
3. **Alcance de la curación manual.** ¿Se transcribe todo el informe o solo lo que se usa?
4. **Analítica.** Sin cookies y con `Plausible`/`Umami` se puede medir sin fricción legal.
