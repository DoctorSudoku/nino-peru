# Mantenimiento

El tablero tiene dos capas con dueños distintos. Confundirlas es la forma más rápida de
que se rompa.

| Capa | Qué es | Quién | Cuándo |
|---|---|---|---|
| **Datos automáticos** | NOAA, ENFEN, INDECI, PRODUCE, prensa, pronóstico | GitHub Actions | cada 3 horas |
| **Datos curados** | cifras del informe técnico del ENFEN | una persona del equipo | cada informe (quincenal) |

Dos roles, aunque sean la misma persona:

- **Responsable editorial**: decide qué se publica, revisa cifras, responde correcciones.
- **Responsable técnico**: mira que el pipeline corra, actualiza dependencias, arregla
  fuentes caídas.

---

## Dependencias de infraestructura

| Pieza | Dónde corre | ¿Hace falta mi computadora? |
|---|---|---|
| Build de datos | GitHub Actions (nube) | **No** |
| Despliegue del sitio | GitHub Pages / Cloudflare / Render | **No** |
| Cron cada 3 h | GitHub Actions | **No** |
| Revisión y edición de datos curados | GitHub (web) o local | Es la única tarea humana |

La computadora solo se usa para **desarrollar** (cambiar código, probar en local) y,
si se prefiere, para editar los datos curados con un editor en vez de la web de GitHub.

> **Aviso**: GitHub desactiva los workflows programados tras 60 días sin ningún commit en
> el repositorio. El workflow incluye un *latido* diario (`.github/latido.txt`) que lo
> evita. Si alguna vez el cron deja de correr sin errores visibles, revisar primero
> **Actions → el workflow → "This workflow was disabled"**.

---

## Rutina

### Diario (2 minutos)

1. Abrir el sitio y comprobar la fecha de "Datos al" en la cabecera. (Se puede hacer
   desde cualquier dispositivo; no requiere la computadora de desarrollo.)
2. Abrir `https://<dominio>/data/meta.json` y revisar `errors` y `sources[].status`.
3. Mirar la pestaña **Actions** del repositorio: si un run falló, aparece en rojo.

Si la fecha no cambió en 12 horas, el pipeline está roto: ver *Playbook*.

### Semanal (15 minutos)

- Revisar qué fuentes fallaron en `meta.json`. Las que fallan dos semanas seguidas
  necesitan arreglo o reemplazo.
- Comprobar que los títulos de prensa siguen siendo pertinentes (el filtro por
  palabras clave puede colar notas deportivas con "niño").
- Revisar la portada en móvil.

### Cada informe del ENFEN (20 minutos)

Este es el único trabajo manual y el que más importa.

1. Abrir <https://enfen.imarpe.gob.pe/informes-tecnicos/> y descargar el informe nuevo.
2. Actualizar `data/curated/enfen_state.json`:
   - `provenance`: documento, corte, fecha de publicación, URL, páginas.
   - `alert`: nivel, magnitud proyectada, próximo comunicado.
   - `indices`: añadir la fila del mes nuevo (ICEN, RONI, ONI y categorías).
   - `forecast`: magnitud y horizontes.
   - `territory`: Titicaca, lluvias, reservorios.
   - `sectors[pesca].datos`: cuota, desembarque, avance, temporada.
3. Si el informe trae tablas nuevas de ríos o embalses:
   ```bash
   PYTHONPATH=.pylibs python3 scripts/extract_enfen_tables.py /ruta/al/informe.pdf
   ```
4. Ejecutar y revisar:
   ```bash
   python3 scripts/build.py
   python3 scripts/check_frescura.py
   python3 -m http.server -d public 8788
   ```
5. Commit y push. El despliegue sale solo.

**Regla de oro:** ninguna cifra curada sin página de referencia. El JSON tiene un
campo `page` para eso. Si no se puede citar, no se publica.

### Mensual (1 hora)

- Actualizar dependencias vendorizadas: `echarts` y `leaflet` (versión fija en
  `public/assets/`). Probar que los gráficos siguen dibujando.
- Revisar que el dominio y el certificado sigan vigentes.
- Copia de seguridad: `data/raw/` y `data/curated/` en un ZIP fuera del repositorio.
- Revisar el glosario: si apareció un término nuevo en el tablero, agregarlo.

---

## Playbook de incidentes

### El ENFEN no resuelve desde GitHub

Es el caso conocido: `enfen.imarpe.gob.pe` resuelve en Perú pero no desde los runners de
GitHub. El build usa el respaldo `data/curated/enfen_documentos.json` y lo marca como
"respaldo" en la tabla de fuentes.

Para actualizar la lista cuando salga un comunicado nuevo, desde una máquina en Perú:

1. `python3 scripts/build.py`
2. Copiar `reports`, `comunicados`, `notas` y `news` desde `public/data/enfen.json`
   hacia `data/curated/enfen_documentos.json`, y actualizar el campo `snapshot`.
3. Commit y push.

### Una fuente dejó de responder

El build no se cae: escribe el error en `meta.json` y conserva el JSON anterior. La
página lo muestra en la tabla de fuentes.

1. Probar la URL a mano (`curl -I <url>`).
2. Si es un cambio de estructura (HTML nuevo, campo renombrado), arreglar el fetcher
   correspondiente en `scripts/build.py`.
3. Si la fuente desapareció, buscar reemplazo en `docs/FUENTES.md` y anotar la decisión.

### El pipeline no corre

1. **Actions** → último run → leer el paso que falló.
2. Causas frecuentes: cambio de estructura en el ENFEN, `pip install pymupdf` lento,
   límite de la API de Open-Meteo.
3. Se puede publicar a mano mientras se arregla:
   ```bash
   ./scripts/publicar.sh
   ```

### Se publicó una cifra equivocada

Es el caso más delicado. Procedimiento:

1. **Corregir primero, explicar después.** Arreglar el dato curado y volver a publicar.
2. Volver a la versión anterior si la corrección tarda: **Actions → run anterior en
   verde → Re-run**, o `git revert` del commit. En Cloudflare sería
   *Deployments → Rollback*.
3. Dejar constancia en el commit: qué estaba mal, qué se corrigió y con qué fuente.
4. Si el error estuvo visible más de una hora, publicar una nota de corrección.

> El historial de git de `data/curated/` es el registro de auditoría. Por eso los
> cambios curados van en commits separados y con mensaje explícito
> (`datos: ICEN set-2026 4,15 / ENFEN N°18 p.26`).

### Pico de tráfico

No requiere acción: el sitio es estático en un CDN. Si un gráfico embebido se vuelve
viral, se sirve desde el borde sin costo extra ni límite práctico.

---

## Señales de que algo se está degradando

| Señal | Qué significa | Acción |
|---|---|---|
| `meta.json` con `errors` no vacío dos días seguidos | una fuente cambió | arreglar el fetcher |
| Fecha del mapa muy atrás | ERDDAP caído y usando el espejo con rezago | esperar; el fallback ya actúa |
| "sin cifras verificables" varios días | los PDF del INDECI vienen con celdas fusionadas | es la deuda conocida del extractor |
| Títulos de prensa irrelevantes | el filtro de palabras clave se quedó corto | ajustar `NEWS_PESOS` / `NEWS_BLOQUEO` en `build.py` |

---

## Deuda técnica conocida

1. **Extractor de daños del INDECI.** La tabla 3.1 no tiene estructura fija; cuando el
   PDF fusiona dos cifras en una celda se descarta el dato. Arreglo: leer por
   coordenadas (x/y de cada palabra) en lugar de confiar en la detección de líneas.
2. **Caché de PDFs.** `data/raw/indeci/` crece sin límite. Conviene purgar lo que tenga
   más de 90 días.
3. **Cifras curadas a mano.** Es intencional, pero significa que el tablero no se
   actualiza solo cuando el ENFEN publica. Automatizar la extracción del informe es el
   siguiente salto de calidad.
4. **Sin pruebas automáticas.** Un test mínimo debería verificar que cada JSON tiene los
   campos esperados antes de publicar.
