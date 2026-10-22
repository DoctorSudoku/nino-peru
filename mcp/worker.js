/**
 * MCP remoto del tablero El Niño · Perú.
 *
 * Implementa Model Context Protocol sobre HTTP (transporte "streamable HTTP")
 * leyendo los JSON públicos que publica GitHub Pages. No guarda estado.
 *
 * Desplegar con:  npx wrangler deploy
 * Endpoint:       https://nino-peru-mcp.<cuenta>.workers.dev/mcp
 */

const DATA_BASE_DEFECTO = "https://doctorsudoku.github.io/nino-peru/data";
let DATA_BASE = DATA_BASE_DEFECTO; // se puede sobreescribir con la variable DATA_BASE
const PROTOCOLO = "2025-06-18";
const VERSION = "1.0.0";
const TTL = 300; // segundos de caché en el borde

const TOOLS = [
  {
    name: "resumen_actual",
    description:
      "Estado vigente de El Niño en el Perú: alerta del ENFEN, ICEN, ONI, anomalía semanal " +
      "del mar y fecha del próximo comunicado oficial.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    run: async () => {
      const [enfen, enso] = await Promise.all([get("enfen.json"), get("enso.json")]);
      const semana = (enfen.weekly?.rows || []).slice(-1)[0] || {};
      const ultimo = (enfen.indices || []).slice(-1)[0] || {};
      return {
        alerta: enfen.alert?.level,
        magnitud_proyectada: enfen.alert?.magnitude_forecast,
        proximo_comunicado: enfen.alert?.next_update,
        icen: { mes: ultimo.month, valor: ultimo.icen, categoria: ultimo.icen_cat },
        oni: { temporada: `${enso.oni_latest?.season} ${enso.oni_latest?.y}`, valor: enso.oni_latest?.anom },
        mar_semana: { fecha: semana.date, nino_1_2: semana.n12a, nino_3_4: semana.n34a },
        pronostico: enfen.forecast,
        fuente: "ENFEN Informe Técnico Año 12 N° 18 (13-oct-2026) y NOAA CPC",
      };
    },
  },
  {
    name: "indices_enso",
    description:
      "Serie mensual de índices ENSO de NOAA: anomalías de Niño 1+2 (costero), 3, 3.4 (global) y 4, " +
      "más el ONI estacional y la lista de episodios de El Niño detectados desde 1950.",
    inputSchema: {
      type: "object",
      properties: {
        ultimos_meses: { type: "integer", minimum: 1, maximum: 900, default: 24 },
      },
      additionalProperties: false,
    },
    run: async ({ ultimos_meses = 24 }) => {
      const enso = await get("enso.json");
      const meses = (enso.monthly || []).slice(-Math.max(1, Math.min(900, ultimos_meses)));
      const f = (m) => `${m.y}-${String(m.m).padStart(2, "0")}`;
      return {
        unidad: "°C de anomalía respecto de 1991-2020",
        desde: meses[0] ? f(meses[0]) : null,
        hasta: meses.at(-1) ? f(meses.at(-1)) : null,
        mensual: meses.map((m) => ({
          mes: f(m), nino12: m.n12a, nino3: m.n3a, nino34: m.n34a, nino4: m.n4a,
        })),
        episodios: (enso.oni_episodes || []).map((e) => ({
          inicio: e.start, fin: e.end, pico: e.peak, cuando: e.peak_label, en_curso: e.ongoing,
        })),
      };
    },
  },
  {
    name: "clima_ciudades",
    description:
      "Pronóstico de cinco días (temperatura máxima/mínima y lluvia) para Lima, Piura, Chiclayo, " +
      "Ica, Iquitos, Arequipa y Cusco. Fuente Open-Meteo; no reemplaza los avisos del SENAMHI.",
    inputSchema: {
      type: "object",
      properties: { ciudad: { type: "string", description: "Filtra por nombre de ciudad" } },
      additionalProperties: false,
    },
    run: async ({ ciudad } = {}) => {
      const p = await get("pronostico.json");
      let ciudades = p.ciudades || [];
      if (ciudad) {
        ciudades = ciudades.filter((c) =>
          c.ciudad.toLowerCase().includes(String(ciudad).toLowerCase()));
      }
      return { fuente: p.fuente, ciudades };
    },
  },
  {
    name: "agua_territorio",
    description:
      "Caudales de los principales ríos y estado de los reservorios según el último informe del ENFEN. " +
      "Permite filtrar por zona: Pacifico Norte, Pacifico Centro, Pacifico Sur o Titicaca.",
    inputSchema: {
      type: "object",
      properties: { zona: { type: "string" } },
      additionalProperties: false,
    },
    run: async ({ zona } = {}) => {
      const agua = await get("agua.json");
      let rios = agua.rios || [];
      if (zona) {
        rios = rios.filter((r) => (r.zona || "").toLowerCase().includes(String(zona).toLowerCase()));
      }
      return {
        rios: rios.map((r) => ({
          rio: r.rio, zona: r.zona, anomalia_pct: r.oct_anom, condicion: r.oct_cond,
        })),
        reservorios: (agua.reservorios || []).map((r) => ({
          nombre: r.reservorio, porcentaje_util: r.pct_util, departamento: r.departamento,
        })),
        fuente: "ENFEN, Tablas 4 y 5 del Informe Técnico N° 18",
      };
    },
  },
  {
    name: "incidencias_recientes",
    description:
      "Reportes de emergencia del INDECI (COEN) de las últimas horas, con departamento, tipo de " +
      "evento y enlace al reporte oficial.",
    inputSchema: {
      type: "object",
      properties: { departamento: { type: "string" } },
      additionalProperties: false,
    },
    run: async ({ departamento } = {}) => {
      const inc = await get("incidencias.json");
      let items = inc.items || [];
      if (departamento) {
        items = items.filter((i) =>
          (i.departamento || "").toLowerCase().includes(String(departamento).toLowerCase()));
      }
      return {
        total: items.length,
        items: items.slice(0, 30).map((i) => ({
          tipo: i.tipo, departamento: i.departamento, distrito: i.distrito,
          fecha: i.fecha, url: i.url,
        })),
        fuente: "INDECI — COEN",
      };
    },
  },
  {
    name: "buscar_datos",
    description: "Lista los conjuntos de datos disponibles y cuándo se actualizaron por última vez.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    run: async () => {
      const [cat, meta] = await Promise.all([get("index.json"), get("meta.json")]);
      return {
        actualizado: cat.generated_at,
        licencia: cat.licencia,
        conjuntos: (cat.endpoints || []).map((e) => ({
          nombre: e.name, url: `${DATA_BASE}/${e.file}`, descripcion: e.desc, campos: e.campos,
        })),
        estado_fuentes: (meta.sources || []).map((s) => ({
          fuente: s.name, ok: s.status?.ok, respaldo: s.status?.backup || false,
        })),
      };
    },
  },
];

const RECURSOS = [
  ["enso.json", "Índices ENSO (NOAA)"],
  ["enfen.json", "Datos del ENFEN"],
  ["agua.json", "Ríos y reservorios"],
  ["incidencias.json", "Emergencias del INDECI"],
  ["pronostico.json", "Pronóstico por ciudad"],
  ["sst.json", "Rejilla de temperatura del mar"],
];

/* ------------------------------------------------------------------ utilidades */

async function get(archivo) {
  const url = `${DATA_BASE}/${archivo}`;
  const cache = typeof caches !== "undefined" ? caches.default : null;
  const key = new Request(url);
  if (cache) {
    const hit = await cache.match(key);
    if (hit) return hit.json();
  }
  const res = await fetch(url, { cf: { cacheTtl: TTL } });
  if (!res.ok) throw new Error(`No se pudo leer ${archivo} (HTTP ${res.status})`);
  const data = await res.json();
  if (cache) {
    await cache.put(key, new Response(JSON.stringify(data), {
      headers: { "content-type": "application/json", "cache-control": `max-age=${TTL}` },
    }));
  }
  return data;
}

const cors = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "POST, GET, OPTIONS",
  "access-control-allow-headers": "content-type, mcp-session-id, authorization",
  "access-control-expose-headers": "mcp-session-id",
};

function json(cuerpo, status = 200) {
  return new Response(JSON.stringify(cuerpo), {
    status,
    headers: { "content-type": "application/json", ...cors },
  });
}

const rpcOk = (id, result) => ({ jsonrpc: "2.0", id, result });
const rpcErr = (id, code, message) => ({ jsonrpc: "2.0", id, error: { code, message } });

async function atender(msg) {
  const { id, method, params = {} } = msg;

  if (method === "initialize") {
    return rpcOk(id, {
      protocolVersion: params.protocolVersion || PROTOCOLO,
      capabilities: { tools: {}, resources: {} },
      serverInfo: { name: "nino-peru", version: VERSION, title: "Tablero El Niño · Perú" },
      instructions:
        "Datos públicos del fenómeno El Niño en el Perú, del tablero del Grupo Evidencia / Media Lamb. " +
        "Fuentes: NOAA CPC (índices ENSO), ENFEN (alerta, ríos y embalses), INDECI (emergencias), " +
        "PRODUCE (descargas de anchoveta) y Open-Meteo (pronóstico). " +
        "Usa resumen_actual para el estado vigente; indices_enso para contexto histórico desde 1950; " +
        "agua_territorio para caudales y reservorios; incidencias_recientes para emergencias; " +
        "clima_ciudades para el pronóstico de los próximos días. " +
        "Las cifras del ENFEN se transcriben con cita de página: el ICEN mide la costa peruana (Niño 1+2) " +
        "y el ONI el Pacífico central (Niño 3.4); no son intercambiables.",
    });
  }
  if (method === "tools/list") return rpcOk(id, { tools: TOOLS.map(({ run, ...t }) => t) });
  if (method === "resources/list") {
    return rpcOk(id, {
      resources: RECURSOS.map(([f, n]) => ({
        uri: `nino-peru://datos/${f}`, name: n, mimeType: "application/json",
      })),
    });
  }
  if (method === "resources/read") {
    const archivo = String(params.uri || "").split("/").pop();
    if (!RECURSOS.some(([f]) => f === archivo)) {
      return rpcErr(id, -32602, `Recurso desconocido: ${params.uri}`);
    }
    const data = await get(archivo);
    return rpcOk(id, {
      contents: [{ uri: params.uri, mimeType: "application/json", text: JSON.stringify(data) }],
    });
  }
  if (method === "tools/call") {
    const tool = TOOLS.find((t) => t.name === params.name);
    if (!tool) return rpcErr(id, -32602, `Herramienta desconocida: ${params.name}`);
    try {
      const salida = await tool.run(params.arguments || {});
      return rpcOk(id, {
        content: [{ type: "text", text: JSON.stringify(salida, null, 1) }],
        isError: false,
      });
    } catch (e) {
      return rpcErr(id, -32603, String(e.message || e));
    }
  }
  if (method === "ping") return rpcOk(id, {});
  return rpcErr(id, -32601, `Método no soportado: ${method}`);
}

/* ---------------------------------------------------------------------- worker */

export default {
  async fetch(request, env) {
    DATA_BASE = (env && env.DATA_BASE) || DATA_BASE_DEFECTO;
    const url = new URL(request.url);

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });

    if (url.pathname === "/mcp" && request.method === "POST") {
      let cuerpo;
      try {
        cuerpo = await request.json();
      } catch {
        return json(rpcErr(null, -32700, "JSON inválido"), 400);
      }
      const mensajes = Array.isArray(cuerpo) ? cuerpo : [cuerpo];
      const salidas = [];
      for (const msg of mensajes) {
        // notificaciones (sin id) no llevan respuesta
        if (msg.id === undefined || msg.id === null) continue;
        salidas.push(await atender(msg));
      }
      if (!salidas.length) return new Response(null, { status: 202, headers: cors });
      return json(Array.isArray(cuerpo) ? salidas : salidas[0]);
    }

    if (url.pathname === "/mcp") {
      return json({ error: "Use POST con JSON-RPC. Transporte: streamable HTTP sin sesión." }, 405);
    }

    if (url.pathname === "/" || url.pathname === "/health") {
      const info = {
        servicio: "MCP — Tablero El Niño · Perú",
        endpoint: `${url.origin}/mcp`,
        protocolo: PROTOCOLO,
        herramientas: TOOLS.map((t) => t.name),
        datos: DATA_BASE,
        version: VERSION,
      };
      if (url.pathname === "/health") return json(info);
      return new Response(
        `<!doctype html><meta charset="utf-8"><title>MCP · El Niño Perú</title>
<style>body{font-family:ui-sans-serif,system-ui,sans-serif;max-width:640px;margin:12vh auto;padding:0 1.5rem;color:#14181d;line-height:1.6}
code{background:#f1efe9;padding:.1rem .35rem;border-radius:4px;font-size:.9em}h1{font-size:1.6rem;margin-bottom:.4rem}
@media(prefers-color-scheme:dark){body{background:#0d1117;color:#eef1f5}code{background:#1b222c}}</style>
<h1>MCP · El Niño Perú</h1>
<p>Endpoint remoto: <code>${url.origin}/mcp</code></p>
<p>Herramientas: ${TOOLS.map((t) => `<code>${t.name}</code>`).join(" ")}</p>
<p>Datos: <a href="${DATA_BASE}/index.json">${DATA_BASE}</a></p>`,
        { headers: { "content-type": "text/html; charset=utf-8" } }
      );
    }

    return json({ error: "Ruta no encontrada" }, 404);
  },
};
