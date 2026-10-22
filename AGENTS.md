# AGENTS.md — instrucciones para agentes que administren este proyecto

Este archivo es el contrato entre el equipo humano y cualquier agente (Hermes, Claude,
Cursor, Copilot u otro) que mantenga el tablero. Léelo completo antes de tocar nada.

**En una frase:** el sitio se publica solo cada 3 horas; un agente solo debe intervenir
cuando algo se rompe, cuando hay que curar un informe del ENFEN o cuando se pide una
mejora explícita.

---

## 1. Qué es este proyecto

Tablero periodístico del fenómeno El Niño en el Perú y el mundo. Sitio estático
(HTML + JSON + ECharts + Leaflet) publicado en GitHub Pages y alimentado por un pipeline
en Python que corre en GitHub Actions.

- **Producción:** <https://doctorsudoku.github.io/nino-peru/>
- **MCP:** <https://nino-peru-mcp.doctorsudoku.workers.dev/mcp>
- **Repositorio:** `DoctorSudoku/nino-peru`

### Mapa del repositorio

```
scripts/build.py              pipeline completo (NOAA, ENFEN, INDECI, PRODUCE, prensa, pronóstico)
scripts/check_frescura.py     verifica que los datos publicados no estén viejos
scripts/fetch_danos.py        cifras de daño desde los PDF del INDECI (PyMuPDF)
scripts/extract_enfen_tables.py  tablas 4 y 5 del informe ENFEN (ríos y embalses)
scripts/mcp_server.py         MCP local por stdio
data/curated/                 ← ÚNICO lugar con datos editados a mano
public/                       lo que se publica (no editar los JSON generados)
mcp/                          Worker de Cloudflare del MCP remoto
docs/                         fuentes, despliegue, mantenimiento, API
interno/                      material de trabajo; NO se publica
```

---

## 2. Reglas que no se rompen

1. **No editar a mano `public/data/*.json`.** Se generan en cada build. Si un dato está
   mal, se corrige en `data/curated/` o en el fetcher.
2. **Ninguna cifra curada sin fuente y página.** Cada valor de `data/curated/enfen_state.json`
   lleva `page` y el bloque `provenance` con documento, corte y URL. Sin eso, no se publica.
3. **No inventar ni interpolar.** Si un valor no está en la fuente, se deja `null` y la
   interfaz lo muestra como ausente. Nunca rellenar con cero.
4. **No tocar `interno/`.** Es material de la sala de redacción y no se publica.
5. **Nunca commitear credenciales.** Los tokens viven en GitHub Secrets
   (`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `RENDER_DEPLOY_HOOK`).
6. **No cambiar el dominio ni `site.config.json` sin pedirlo.** Rompe sitemap, robots y
   los embebibles.
7. **Toda modificación de código va en una rama y un PR.** `main` publica al instante.
8. **Los cambios de datos curados van en commits separados**, con mensaje explícito:
   `datos: ICEN set-2026 4,15 / ENFEN N°18 p.26`. Ese historial es la auditoría.

---

## 3. Comandos de trabajo

```bash
# entorno (una vez)
python3 -m pip install --target .pylibs pymupdf

# construir datos y verificar
PYTHONPATH=.pylibs python3 scripts/build.py
python3 scripts/check_frescura.py

# ver el sitio en local
python3 -m http.server -d public 8788
```

**Criterio de éxito de un cambio:**

- `scripts/build.py` termina con código 0 y sin `FALTAN DATOS ESENCIALES`.
- `check_frescura.py` imprime "Datos frescos."
- La portada carga en `http://127.0.0.1:8788/` y las consolas del navegador no muestran errores.
- Los cuatro endpoints responden: `/data/enso.json`, `/data/enfen.json`, `/data/sst.json`, `/data/meta.json`.

---

## 4. Qué puede hacer un agente solo

| Tarea | Autonomía |
|---|---|
| Arreglar un fetcher roto (cambió el HTML de una fuente) | **Sí**, con PR |
| Ajustar el filtro de noticias, colores, textos, accesibilidad | **Sí**, con PR |
| Actualizar dependencias vendorizadas (ECharts, Leaflet) | **Sí**, con PR y prueba visual |
| Añadir una fuente nueva con su fetcher y su fila en `docs/FUENTES.md` | **Sí**, con PR |
| Actualizar `data/curated/enfen_state.json` con un informe nuevo | **Requiere revisión humana** antes de mergear |
| Cambiar el dominio, el hosting o la licencia | **No.** Preguntar |
| Tocar `interno/`, credenciales o configuración de la cuenta de GitHub/Cloudflare | **No.** |
| Publicar una corrección de una cifra ya publicada | **Sí**, pero avisar en el mismo PR y dejar constancia del error |

Todo PR debe explicar: qué cambió, por qué, qué fuente lo respalda y cómo se verificó.

---

## 5. Playbooks

### Una fuente dejó de responder

El build no se cae: anota el error en `data/meta.json` y conserva el JSON anterior.

1. Comprobar la URL a mano.
2. Si cambió la estructura, arreglar el fetcher en `scripts/build.py`.
3. Si la fuente desapareció, buscar reemplazo y documentarlo en `docs/FUENTES.md`.
4. Si es el ENFEN, ver la sección 6.

### El build falla en CI

1. Leer la anotación del run en GitHub (el workflow publica el error como `::error::`).
2. Reproducir en limpio:
   ```bash
   git clone <repo> /tmp/prueba && cd /tmp/prueba && PYTHONPATH=<repo>/.pylibs python3 scripts/build.py
   ```
3. Causas vistas antes: dominio que no resuelve desde GitHub, tabla del PDF con celdas
   fusionadas, timeout de PRODUCE.

### Se publicó una cifra equivocada

1. Corregir primero: `data/curated/` y PR con la corrección.
2. Si tarda, revertir el despliegue (Actions → run anterior → Re-run).
3. Registrar en el commit qué estaba mal y con qué fuente se corrigió.
4. Si estuvo visible más de una hora, proponer una nota de corrección.

### Llega un informe nuevo del ENFEN

1. Obtener el PDF (ver sección 6 si el dominio no resuelve).
2. Actualizar `data/curated/enfen_state.json`: `provenance`, `alert`, `indices`, `forecast`,
   `territory`, `sectors[pesca].datos`.
3. Si trae tablas de ríos o embalses:
   `PYTHONPATH=.pylibs python3 scripts/extract_enfen_tables.py /ruta/informe.pdf`
4. Refrescar `data/curated/enfen_documentos.json` (comunicados e informes).
5. `build.py` + `check_frescura.py`, revisar en local, PR.

---

## 6. Limitación conocida: el ENFEN no resuelve desde la nube

`enfen.imarpe.gob.pe` resuelve en Perú pero **no** desde los runners de GitHub ni,
probablemente, desde el entorno donde corra el agente. Por eso existe
`data/curated/enfen_documentos.json`: una copia fechada de comunicados e informes.

Para actualizarla hace falta una de estas tres vías:

1. Ejecutar el build desde una máquina en Perú y commitear el archivo.
2. Usar el espejo de MINAM: `https://sinia.minam.gob.pe/` publica los informes del ENFEN.
3. Pedirle el PDF a una persona del equipo y extraer las cifras a mano.

Si el agente no puede resolver el dominio, **no debe inventar la lista de documentos**:
deja el respaldo como está y lo informa.

---

## 7. Contratos de datos

Los JSON publicados son una API pública documentada en `docs/API.md`. Reglas:

- Unidades: °C para temperatura y anomalías; % para caudales y embalses.
- Ausencia de dato: `null`, nunca `0`.
- Fechas: ISO 8601 con zona horaria de Lima.
- Valores `*_tmp`: estimaciones en tiempo real del ENFEN, se revisan al informe siguiente.
- **No romper campos existentes.** Agregar es seguro; renombrar o quitar rompe a los
  consumidores (incluido el MCP y los embebibles).

---

## 8. Cómo reportar

- Un PR por tema, con título en español y descripción breve.
- Si el agente no puede completar algo, lo dice explícitamente y explica qué falta.
- No dejar TODOs silenciosos en el código: si algo queda pendiente, va a `docs/PLAN.md`.

---

## 9. Contacto y escalamiento

- Decisiones editoriales (qué se publica, cómo se redacta): responsable editorial humano.
- Accesos, facturación, cuentas: nunca delegar.
- Ante duda sobre una cifra: preguntar antes de publicar. Un dato sin fuente es peor
  que un dato ausente.
