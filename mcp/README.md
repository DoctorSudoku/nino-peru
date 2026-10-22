# MCP remoto

Servidor **Model Context Protocol** público para consultar los datos del tablero desde
ChatGPT, Claude, Cursor o cualquier cliente compatible.

El sitio en GitHub Pages no puede ejecutar código, así que el MCP vive aparte: un
*Worker* de Cloudflare (plan gratuito, sin arranque en frío) que lee los JSON publicados.

```
Cliente MCP  ──HTTP──▶  Worker /mcp  ──fetch──▶  doctorsudoku.github.io/nino-peru/data/*.json
```

## Desplegar (5 minutos, gratis)

```bash
cd mcp
npx wrangler login      # abre el navegador, crea o usa tu cuenta de Cloudflare
npx wrangler deploy
```

Al terminar imprime la URL:

```
https://nino-peru-mcp.TU-SUBDOMINIO.workers.dev/mcp
```

Probar sin desplegar, en local:

```bash
npx wrangler dev        # http://localhost:8787/mcp
```

## Conectar un cliente

**Claude Code / Cursor (transporte HTTP):**

```bash
claude mcp add --transport http nino-peru https://nino-peru-mcp.TU-SUBDOMINIO.workers.dev/mcp
```

**Clientes que solo hablan stdio** (Claude Desktop y otros), mediante puente:

```json
{
  "mcpServers": {
    "nino-peru": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://nino-peru-mcp.TU-SUBDOMINIO.workers.dev/mcp"]
    }
  }
}
```

**Prueba manual** con `curl`:

```bash
curl -sS https://nino-peru-mcp.TU-SUBDOMINIO.workers.dev/mcp \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"resumen_actual","arguments":{}}}'
```

## Herramientas

| Nombre | Para qué | Argumentos |
|---|---|---|
| `resumen_actual` | Alerta, ICEN, ONI y anomalía semanal | — |
| `indices_enso` | Serie mensual de NOAA y episodios desde 1950 | `ultimos_meses` |
| `clima_ciudades` | Pronóstico de 5 días en 7 ciudades | `ciudad` |
| `agua_territorio` | Caudales de ríos y reservorios | `zona` |
| `incidencias_recientes` | Emergencias del INDECI | `departamento` |
| `buscar_datos` | Catálogo de conjuntos y estado de fuentes | — |

También expone los JSON como **recursos** (`nino-peru://datos/enfen.json`, etc.) para
clientes que prefieren leer archivos completos.

## Límites y decisiones

- **Sin estado ni sesiones**: cada POST es independiente. No se guarda nada del usuario.
- **Caché de 5 minutos** en el borde de Cloudflare.
- **Plan gratuito**: 100 000 peticiones diarias.
- **Sin autenticación**: los datos ya son públicos. Si algún día se añade una herramienta
  con datos internos, habría que ponerle token.
- El Worker **no** depende del sitio: si GitHub Pages cae, responde con error explícito.

## Si cambia el dominio del tablero

Editar `[vars] DATA_BASE` en `wrangler.toml` y volver a desplegar. No hay nada más
acoplado: el Worker solo conoce esa URL.

## Costo

0 USD. El Worker y las lecturas del sitio entran en el plan gratuito.
