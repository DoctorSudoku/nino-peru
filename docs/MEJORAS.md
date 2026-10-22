# Mejoras sobre la referencia

Análisis de `observatorio-nino-peru.onrender.com` (Grupo Evidencia · MNRY), revisado el
21 de octubre de 2026, y qué podemos hacer distinto.

## Lo que hace bien esa referencia

- **Datos en vivo, no solo clima:** suma GDACS (emergencias), Open-Meteo (pronóstico de
  7 días), INDECI y titulares de prensa. Le da uso diario, no solo en alerta.
- **Mapa multicapa:** temperatura del mar, lluvia esperada y emergencias en un solo lugar.
- **Explica la escala:** cada índice trae su «¿Qué significa?» con los umbrales. Es la
  mejor decisión de diseño del sitio.
- **Fuente por dato:** muestra el estado de cada fuente y asume el fallo («—»).
- **MCP:** permite que un asistente de IA consulte los datos. Es una ventaja de
  distribución que casi nadie tiene.
- **Modo oscuro nativo:** la identidad visual está pensada en oscuro.

## Dónde podemos ser mejores

| # | Mejora | Por qué | Costo |
|---|---|---|---|
| 1 | **Contexto histórico, no solo el último año** | Su gráfico cubre 12 meses. Sin 1982–83, 1997–98 y 2015–16 no se puede decir si esto es grande o enorme. Nosotros ya tenemos 1950–2026 y el comparador alineado por mes de inicio. | bajo (hecho) |
| 2 | **Percentil del episodio** | Una frase que un editor puede citar: «noveno episodio más intenso desde 1950». Se calcula con la misma serie. | bajo |
| 3 | **Mapa con dato, no con imagen** | Su capa de temperatura es una imagen. La nuestra es rejilla OISST (0,25°) con valor al pasar el cursor y cajas Niño 1+2/3/3.4/4 dibujadas. | medio (hecho) |
| 4 | **Sectores económicos** | Agro, pesca, agua/energía y precios. Es el ángulo que ningún observatorio cubre y el que usan los medios de economía. | alto (fase 1) |
| 5 | **Trazabilidad con página** | Cada cifra curada cita informe y página; el JSON es descargable. Permite auditar y citar en un juicio editorial. | bajo (hecho) |
| 6 | **Modo claro y oscuro** | Ellos son solo oscuro. Un tablero que se proyecta en una sala de redacción o se imprime necesita claro. | bajo (hecho) |
| 7 | **Textos para redes** | Genera tres textos listos con las cifras del día. Ahorra el paso más lento de la rutina periodística. | bajo (hecho) |
| 8 | **Alertas proactivas** | Correo/Telegram cuando el ENFEN publica o el ICEN cruza un umbral. Convierte el tablero en servicio, no en consulta. | medio |
| 9 | **Ficha descargable por episodio** | PDF/PNG con la situación y la fuente, para públicos y conferencias. | medio |
| 10 | **Embebibles por gráfico** | `<iframe>` por visualización para que otros medios citen el trabajo y llegue el crédito. | bajo |
| 11 | **Frescura del mapa** | OISST NRT llega a ayer; MUR (1 km, NASA/JPL) o Coral Reef Watch (5 km) dan más detalle costero. | medio |
| 12 | **Accesibilidad y SEO** | Tablas equivalentes, contraste AA, datos estructurados, «última actualización» visible. | bajo |

## Lo que la referencia tiene y nosotros deberíamos tomar

1. **Pronóstico de lluvia a 7 días** (Open-Meteo, gratis y sin clave) por ciudad: es lo
   que la gente busca cuando hay alerta.
2. **GDACS**: da emergencias con impacto real y cobertura mundial; complementa a INDECI.
3. **Titulares de prensa** con enlace al original: contexto, no dato.
4. **«¿Qué significa?»** junto a cada índice, en lenguaje llano.
5. **Una API/MCP** para que otros reutilicen los datos. Bajo costo, alto retorno.

## Colaboración en vez de duplicación

Los dos sitios usan las mismas fuentes primarias. Tiene más sentido **compartir el
pipeline de datos** (un JSON público y versionado) y diferenciarse en la capa editorial:
ellos en vivo y operativo, nosotros en contexto histórico y sectores. Duplicar el
scraping del ENFEN es trabajo perdido para ambos.
