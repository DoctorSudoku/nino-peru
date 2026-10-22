/* ==================================================================
   Tablero El Niño · Perú — capa de presentación
   Lee los JSON de scripts/build.py. Dependencias: ECharts + Leaflet.
   ================================================================== */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const MONTH_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"];
const MONTH_LONG = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
  "setiembre", "octubre", "noviembre", "diciembre"];

const nf = (d) => new Intl.NumberFormat("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d });
const signed = (v, d = 2) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${nf(d).format(Math.abs(v))}`;

const monthLabel = (iso, long = false) => {
  const [y, m] = iso.split("-").map(Number);
  return long ? `${MONTH_LONG[m - 1]} de ${y}` : `${MONTH_ES[m - 1]} ${y}`;
};
const dateLabel = (iso) => {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} de ${MONTH_LONG[m - 1]} de ${y}`;
};

const cssv = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const theme = () => document.documentElement.getAttribute("data-theme") || "light";

/** La magnitud del ENFEN viene en femenino ("Extraordinaria", por "magnitud").
 *  Aplicada a "El Niño costero" necesita el masculino. */
const MAG_MASC = {
  extraordinaria: "extraordinario", "muy fuerte": "muy fuerte", fuerte: "fuerte",
  moderada: "moderado", "débil": "débil", debil: "débil",
};
const magMasculino = (m) => MAG_MASC[String(m).toLowerCase().trim()] || String(m).toLowerCase();

const catClass = (cat = "") => {
  const c = cat.toLowerCase();
  if (c.includes("extraordinaria") || c.includes("muy fuerte")) return "tag-warm3";
  if (c.includes("fuerte")) return "tag-warm2";
  if (c.includes("moderada") || c.includes("cálida débil")) return "tag-warm1";
  if (c.includes("fría")) return "tag-cold";
  return "tag-neutral";
};
const tag = (text, cls) => `<span class="tag ${cls}">${text}</span>`;

/** "1982-08"→"1983-06" = "1982–83"; un solo año = "2026" */
function epName(e) {
  const y1 = Number(e.start.slice(0, 4));
  const y2 = Number(e.end.slice(0, 4));
  return y1 === y2 ? `${y1}` : `${y1}–${String(y2).slice(2)}`;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove("show"), 2100);
}

async function loadJSON(path) {
  const res = await fetch(path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json();
}

/* ======================================================================
   Mapa de temperatura del mar
   ====================================================================== */

const ANOM_STOPS = [
  [-3, [27, 58, 143]], [-2, [42, 95, 196]], [-1, [74, 144, 217]], [-0.5, [146, 197, 233]],
  [0, [233, 238, 242]], [0.75, [250, 222, 180]], [1.5, [244, 172, 105]], [2.5, [228, 96, 55]],
  [3.5, [190, 40, 26]], [5, [128, 12, 10]], [6, [74, 5, 6]],
];
const SST_STOPS = [
  [14, [18, 58, 99]], [18, [42, 111, 158]], [22, [87, 167, 184]], [24, [168, 216, 185]],
  [26, [242, 224, 138]], [28, [237, 164, 92]], [30, [216, 84, 47]], [32, [143, 26, 16]],
];

function lerpColor(stops, v) {
  if (v <= stops[0][0]) return stops[0][1];
  if (v >= stops[stops.length - 1][0]) return stops[stops.length - 1][1];
  for (let i = 1; i < stops.length; i++) {
    if (v <= stops[i][0]) {
      const [v0, c0] = stops[i - 1];
      const [v1, c1] = stops[i];
      const t = (v - v0) / (v1 - v0);
      return c0.map((ch, k) => Math.round(ch + (c1[k] - ch) * t));
    }
  }
  return stops[stops.length - 1][1];
}
const rgb = (c) => `rgb(${c[0]},${c[1]},${c[2]})`;
const normLon = (lon) => ((((lon + 180) % 360) + 360) % 360) - 180;

const NINO_BOXES = [
  { id: "1+2", label: "Niño 1+2 (costero)", lat: [-10, 0], lon: [-90, -80], always: true },
  { id: "3", label: "Niño 3", lat: [-5, 5], lon: [-150, -90], always: false },
  { id: "3.4", label: "Niño 3.4 (global)", lat: [-5, 5], lon: [-170, -120], always: false },
  { id: "4", label: "Niño 4", lat: [-5, 5], lon: [160, 180], always: false },
  { id: "4", label: "Niño 4", lat: [-5, 5], lon: [-180, -150], always: false },
];

const MapModule = {
  map: null,
  canvas: null,
  ctx: null,
  tiles: null,
  boxKey: "peru",
  mapvar: "anom",
  data: null,
  tip: null,

  init(sst) {
    this.data = sst;
    const el = $("#map");
    if (!el || !window.L) return;

    el.innerHTML = "";
    const map = L.map(el, {
      center: [-9.5, -79.5], zoom: 5, zoomSnap: 0.25, minZoom: 1.5, maxZoom: 8,
      zoomControl: true, attributionControl: true, worldCopyJump: false, preferCanvas: true,
    });
    L.control.zoom({ position: "bottomright" }).addTo(map);
    map.zoomControl.remove();
    this.map = map;

    // tooltip propio
    const tip = document.createElement("div");
    tip.className = "map-tip";
    el.appendChild(tip);
    this.tip = tip;

    this.addTiles();
    this.addCanvas();
    this.addNinoBoxes();
    const view = new URLSearchParams(location.search).get("view");
    this.fit(view === "pacifico" ? "pacifico" : "peru");
    this.bindEvents();

    $("#map-date").textContent = sst.date ? `al ${dateLabel(sst.date)} · NOAA OISST` : "sin datos";
    this.drawLegend();

    map.whenReady(() => { map.invalidateSize(); this.draw(); this.drawNinoLabels(); });
    map.on("load", () => { this.draw(); this.drawNinoLabels(); });
    map.on("mousemove", (e) => this.hover(e));
    map.on("mouseout", () => this.tip.classList.remove("show"));
    map.on("moveend zoomend resize", () => this.draw());
    map.on("zoomend moveend resize", () => this.drawNinoLabels());
  },

  addTiles() {
    const dark = theme() === "dark";
    const service = dark ? "World_Dark_Gray_Base" : "World_Light_Gray_Base";
    const layer = L.tileLayer(
      `https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/${service}/MapServer/tile/{z}/{y}/{x}`,
      { maxZoom: 8, opacity: 1, attribution: '© Esri · HERE · Garmin · OpenStreetMap · datos NOAA OISST' }
    );
    layer.addTo(this.map);
    this.tiles = layer;
  },

  refreshTheme() {
    if (!this.map) return;
    if (this.tiles) this.map.removeLayer(this.tiles);
    this.addTiles();
    this.draw();
    this.drawNinoLabels();
  },

  addCanvas() {
    const canvas = document.createElement("canvas");
    canvas.className = "leaflet-zoom-animated";
    canvas.style.position = "absolute";
    canvas.style.top = "0";
    canvas.style.left = "0";
    this.map.getPane("overlayPane").appendChild(canvas);
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
  },

  box() {
    const b = this.data?.boxes?.[this.boxKey];
    return b && b.anom ? b : null;
  },

  values() {
    const b = this.box();
    if (!b) return null;
    return this.mapvar === "sst" && b.sst ? b.sst : b.anom;
  },

  fit(key) {
    this.boxKey = key;
    if (key === "pacifico") {
      this.map.setView([-5, -155], 2.3, { animate: false });
    } else {
      this.map.setView([-9.5, -79.5], 5, { animate: false });
    }
    this.draw();
    this.drawLegend();
    $("#map-zoom").textContent = key === "pacifico" ? "← Volver al Perú" : "Ver todo el Pacífico →";
    $$("[data-mapvar]").forEach((b) => {
      const disabled = key === "pacifico" && b.dataset.mapvar === "sst";
      b.disabled = disabled;
      b.style.opacity = disabled ? ".4" : "1";
    });
    this.addNinoBoxes();
    this.drawNinoLabels();
  },

  draw() {
    const map = this.map, canvas = this.canvas;
    if (!map || !canvas) return;
    const box = this.box(), vals = this.values();
    const size = map.getSize(), dpr = Math.min(window.devicePixelRatio || 1, 2);
    const topLeft = map.containerPointToLayerPoint([0, 0]);
    L.DomUtil.setPosition(canvas, topLeft);
    canvas.width = size.x * dpr;
    canvas.height = size.y * dpr;
    canvas.style.width = `${size.x}px`;
    canvas.style.height = `${size.y}px`;

    const ctx = this.ctx;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.x, size.y);
    if (!box || !vals) return;

    const z = map.getZoom();
    const stride = z < 3 ? 4 : z < 4.5 ? 2 : 1;
    const half = box.step / 2;
    const stops = this.mapvar === "sst" && box.sst ? SST_STOPS : ANOM_STOPS;

    for (let i = 0; i < box.nlat; i += stride) {
      for (let j = 0; j < box.nlon; j += stride) {
        const v = vals[i * box.nlon + j];
        if (v === null || v === undefined) continue;
        const lat = box.lat0 + i * box.step;
        const lon = normLon(box.lon0 + j * box.step);
        const cell = box.step * stride;
        const a = map.latLngToLayerPoint([lat - cell / 2, lon - cell / 2]).subtract(topLeft);
        const b = map.latLngToLayerPoint([lat + cell / 2, lon + cell / 2]).subtract(topLeft);
        const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y);
        const w = Math.abs(b.x - a.x), h = Math.abs(b.y - a.y);
        if (x > size.x || y > size.y || x + w < 0 || y + h < 0) continue;
        ctx.fillStyle = rgb(lerpColor(stops, v));
        ctx.fillRect(x, y, Math.max(1, w + 0.6), Math.max(1, h + 0.6));
      }
    }
  },

  addNinoBoxes() {
    const map = this.map;
    if (!map) return;
    if (this._boxes) this._boxes.forEach((l) => map.removeLayer(l));
    this._boxes = [];
    const showAll = this.boxKey === "pacifico";
    NINO_BOXES.filter((b) => b.always || showAll).forEach((b) => {
      const r = L.rectangle([[b.lat[0], b.lon[0]], [b.lat[1], b.lon[1]]], {
        color: cssv("--ink"), weight: 1, dashArray: "5 4", fill: false, opacity: 0.55, interactive: false,
      }).addTo(map);
      this._boxes.push(r);
    });
  },

  drawNinoLabels() {
    const map = this.map;
    if (!map) return;
    if (this._labels) this._labels.forEach((m) => map.removeLayer(m));
    this._labels = [];
    const showAll = this.boxKey === "pacifico";
    NINO_BOXES.filter((b) => (b.always || showAll) && b.lon[0] < 180).forEach((b) => {
      const marker = L.marker([(b.lat[0] + b.lat[1]) / 2, (b.lon[0] + b.lon[1]) / 2], {
        interactive: false,
        icon: L.divIcon({ className: "nino-label", html: b.label || `Niño ${b.id}`, iconSize: [96, 14] }),
      }).addTo(map);
      this._labels.push(marker);
    });
  },

  drawLegend() {
    const el = $("#map-legend");
    if (!el) return;
    const isSst = this.mapvar === "sst" && this.box()?.sst && this.boxKey === "peru";
    const stops = isSst ? SST_STOPS : ANOM_STOPS;
    const lo = stops[0][0], hi = stops[stops.length - 1][0];
    const grad = stops.map(([v, c]) => `${rgb(c)} ${((v - lo) / (hi - lo) * 100).toFixed(1)}%`).join(", ");
    const ticks = isSst ? [14, 18, 22, 26, 30, 32] : [-3, -2, -1, 0, 1, 2, 3, 4, 5];
    const labels = ticks.map((t) => {
      const pct = ((t - lo) / (hi - lo)) * 100;
      const txt = `${t > 0 && !isSst ? "+" : ""}${String(t).replace(".", ",")}`;
      return `<span style="left:${pct}%">${txt}</span>`;
    }).join("");
    el.innerHTML = `
      <p class="legend-title">${isSst ? "Temperatura del mar (°C)" : "Anomalía: cuánto se aparta de lo normal (°C)"}</p>
      <div class="legend-bar" style="background:linear-gradient(90deg,${grad})"></div>
      <div class="legend-labels">${labels}</div>`;
  },

  hover(e) {
    const box = this.box(), vals = this.values();
    if (!box || !vals) return;
    const lon360 = e.latlng.lng < 0 ? e.latlng.lng + 360 : e.latlng.lng;
    const j = Math.round((lon360 - box.lon0) / box.step);
    const i = Math.round((e.latlng.lat - box.lat0) / box.step);
    const tip = this.tip;
    if (i < 0 || j < 0 || i >= box.nlat || j >= box.nlon) {
      tip.classList.remove("show");
      return;
    }
    const v = vals[i * box.nlon + j];
    if (v === null || v === undefined) {
      tip.classList.remove("show");
      return;
    }
    const lat = box.lat0 + i * box.step, lon = normLon(box.lon0 + j * box.step);
    const region = NINO_BOXES.find((b) =>
      lat >= b.lat[0] && lat <= b.lat[1] && lon >= b.lon[0] && lon <= b.lon[1]);
    let txt = this.mapvar === "sst" && box.sst ? `${nf(1).format(v)} °C` : `${signed(v, 1)} °C`;
    const anom = box.anom[i * box.nlon + j];
    if (this.mapvar === "sst" && anom !== null && anom !== undefined) txt += ` · ${signed(anom, 1)} vs. normal`;
    if (region) txt += ` · ${region.label || "Niño " + region.id}`;
    tip.innerHTML = `${txt}<br><span style="opacity:.65">${nf(1).format(Math.abs(lat))}°${lat < 0 ? "S" : "N"} ${nf(0).format(Math.abs(lon))}°${lon < 0 ? "O" : "E"}</span>`;
    const p = this.map.latLngToContainerPoint(e.latlng);
    tip.style.left = `${p.x}px`;
    tip.style.top = `${p.y}px`;
    tip.classList.add("show");
  },

  bindEvents() {
    $$("[data-mapvar]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.disabled) return;
        this.mapvar = btn.dataset.mapvar;
        $$("[data-mapvar]").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
        this.draw();
        this.drawLegend();
      });
    });
    $("#map-zoom")?.addEventListener("click", () => {
      this.fit(this.boxKey === "peru" ? "pacifico" : "peru");
    });
  },
};

/* ======================================================================
   KPIs y textos de portada
   ====================================================================== */

function renderKPIs(enso, enfen) {
  const lastIdx = enfen.indices[enfen.indices.length - 1];
  const oni = enso.oni_latest;
  const week = (enfen.weekly?.rows || []).slice(-1)[0];
  const next = enfen.alert?.next_update;

  const cards = [
    { label: "ICEN · costa peruana (ENFEN)", value: signed(lastIdx.icen), unit: "°C", badge: lastIdx.icen_cat, note: `Mes de ${monthLabel(lastIdx.month)} · provisional`, hot: true },
    { label: "ONI · Pacífico central (NOAA)", value: signed(oni.anom), unit: "°C", badge: lastIdx.oni_cat, note: `Temporada ${oni.season} ${oni.y} · media de 3 meses`, hot: true },
    { label: "Mar frente a la costa · Niño 1+2", value: week ? signed(week.n12a, 1) : "—", unit: "°C", badge: week ? `Niño 3.4: ${signed(week.n34a, 1)}` : "", note: week ? `Semana del ${dateLabel(week.date)} · OISST` : "" },
    { label: "Próximo comunicado", value: next ? next.slice(8, 10) : "—", unit: next ? MONTH_ES[Number(next.slice(5, 7)) - 1] : "", badge: "ENFEN", note: `Informe N° 18 · ${dateLabel(enfen.provenance?.cutoff)}` },
  ];

  $("#kpis").innerHTML = cards.map((c) => `
    <div class="kpi${c.hot ? " kpi-hot" : ""}">
      <p class="kpi-label">${c.label}</p>
      <div class="kpi-value">${c.value}<small> ${c.unit}</small></div>
      ${c.badge ? `<span class="kpi-badge">${c.badge}</span>` : ""}
      <p class="kpi-note">${c.note}</p>
    </div>`).join("");

  $("#alert-text").textContent = "El Niño costero · extraordinario";
  $("#top-cutoff").textContent = dateLabel(enfen.provenance?.cutoff);

  // portada
  const mag = enfen.alert?.magnitude_forecast || "extraordinaria";
  const titleEl = $("#hero-title");
  if (titleEl && week) {
    titleEl.innerHTML = `El mar frente al Perú está <em>${nf(1).format(Math.abs(week.n12a))} °C</em> sobre lo normal`;
  }
  // Sin esto, la cifra del titular (semanal) y la del ICEN (mensual) parecen la misma medición.
  const metaEl = $("#hero-meta");
  if (metaEl) {
    metaEl.innerHTML = week
      ? `Semana del <b>${dateLabel(week.date)}</b> (OISST). Cifra mensual oficial: ` +
        `<b>ICEN ${signed(lastIdx.icen)} °C</b>, ${monthLabel(lastIdx.month)} (ENFEN).`
      : "";
  }
  $("#hero-lede").innerHTML =
    `El ENFEN mantiene la alerta máxima: El Niño costero es <strong>${magMasculino(mag)}</strong> y seguiría así hasta ${monthLabel("2027-01", true)}.`;

  // banda ENFEN
  const com = enfen.latest_comunicado;
  if (com) {
    $("#enfen-link").textContent = com.title;
    $("#enfen-link").href = com.url;
    $("#enfen-btn").href = com.url;
  }
  const fc = enfen.forecast?.[0];
  $("#enfen-summary").textContent = fc
    ? `Magnitud ${fc.magnitude.toLowerCase()} hasta ${monthLabel(fc.until, true)}.`
    : "—";
  $("#enfen-next").textContent = dateLabel(enfen.alert?.next_update);
}

/* ======================================================================
   Gráficos
   ====================================================================== */

const Charts = { indices: null, history: null, compare: null, rios: null, reservorios: null, agro: null, pesca: null };

function chartBase() {
  return {
    backgroundColor: "transparent",
    textStyle: { fontFamily: "inherit", color: cssv("--ink-2") },
  };
}

function renderIndicesChart(enfen) {
  const el = $("#chart-indices");
  if (!el) return;
  if (Charts.indices) Charts.indices.dispose();
  const chart = echarts.init(el, null, { renderer: "canvas" });
  Charts.indices = chart;

  const rows = enfen.indices;
  const narrow = window.innerWidth < 620;
  const ink3 = cssv("--ink-3"), line = cssv("--line");

  chart.setOption({
    ...chartBase(),
    grid: { left: narrow ? 36 : 44, right: narrow ? 10 : 26, top: 30, bottom: 30 },
    tooltip: {
      trigger: "axis", valueFormatter: (v) => `${signed(v)} °C`,
      axisPointer: { type: "line", lineStyle: { color: ink3 } },
      backgroundColor: cssv("--surface"), borderColor: line, textStyle: { color: cssv("--ink") },
    },
    legend: { top: 0, right: 8, itemWidth: 10, itemHeight: 10, textStyle: { color: ink3, fontSize: 11 } },
    xAxis: {
      type: "category", data: rows.map((r) => monthLabel(r.month)), boundaryGap: false,
      axisLine: { lineStyle: { color: line } },
      axisLabel: { color: ink3, fontSize: 10, interval: narrow ? 3 : 1 },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value", min: 0, max: 4.6,
      splitLine: { lineStyle: { color: cssv("--line-2") } },
      axisLabel: { color: ink3, fontSize: 10, formatter: (v) => `${nf(1).format(v)}°` },
    },
    series: [
      {
        name: "ICEN", type: "line", data: rows.map((r) => r.icen),
        symbol: "circle", symbolSize: 5, lineStyle: { width: 2.6, color: cssv("--accent") },
        itemStyle: { color: cssv("--accent") },
        markLine: {
          silent: true, symbol: "none",
          label: { position: "insideStartTop", color: ink3, fontSize: 9 },
          lineStyle: { color: line, type: "dashed", width: 1 },
          data: [{ yAxis: 0.5, name: "débil" }, { yAxis: 1.5, name: "fuerte" }, { yAxis: 2.5, name: "extraordinaria" }],
        },
      },
      { name: "RONI", type: "line", data: rows.map((r) => r.roni), symbol: "circle", symbolSize: 4, lineStyle: { width: 1.5, color: "#e8703a" }, itemStyle: { color: "#e8703a" } },
      { name: "ONI", type: "line", data: rows.map((r) => r.oni), symbol: "circle", symbolSize: 4, lineStyle: { width: 1.5, color: cssv("--cool"), type: "dashed" }, itemStyle: { color: cssv("--cool") } },
    ],
  }, true);

  $("#note-indices").textContent =
    `ENFEN: débil 0,5 · moderada 1,0 · fuerte 1,5 · extraordinaria 2,5 °C. Último dato: ${monthLabel(rows.at(-1).month)}.`;
}

function oniPointDate(r) {
  const center = { DJF: 0, JFM: 1, FMA: 2, MAM: 3, AMJ: 4, MJJ: 5, JJA: 6, JAS: 7, ASO: 8, SON: 9, OND: 10, NDJ: 11 }[r.season];
  return new Date(r.y, center, 15);
}

function renderHistory(enso, mode = "oni") {
  const el = $("#chart-history");
  if (!el) return;
  if (Charts.history) Charts.history.dispose();
  const chart = echarts.init(el, null, { renderer: "canvas" });
  Charts.history = chart;

  const ink3 = cssv("--ink-3"), line = cssv("--line"), line2 = cssv("--line-2");
  const isOni = mode === "oni";
  const data = isOni
    ? enso.oni.map((r) => [oniPointDate(r).getTime(), r.anom])
    : enso.monthly.map((r) => [new Date(r.y, r.m - 1, 15).getTime(), r.n12a]);

  const episodes = isOni ? enso.oni_episodes.filter((e) => e.peak >= 1.7) : [];
  const markAreas = episodes.map((e) => {
    const [sy, sm] = e.start.split("-").map(Number);
    const [ey, em] = e.end.split("-").map(Number);
    return [
      { name: epName(e), xAxis: new Date(sy, sm - 1, 1).getTime(), itemStyle: { color: "rgba(179,38,30,0.07)" },
        label: { show: e.peak >= 2, position: "insideTop", color: cssv("--accent"), fontSize: 10, fontWeight: 600 } },
      { xAxis: new Date(ey, em - 1, 28).getTime() },
    ];
  });

  chart.setOption({
    ...chartBase(),
    grid: { left: 44, right: 18, top: 22, bottom: 54 },
    tooltip: {
      trigger: "axis", axisPointer: { type: "line", lineStyle: { color: ink3 } },
      backgroundColor: cssv("--surface"), borderColor: line, textStyle: { color: cssv("--ink") },
      formatter: (params) => {
        const d = new Date(params[0].value[0]);
        return `<strong>${MONTH_LONG[d.getMonth()]} ${d.getFullYear()}</strong><br>${signed(params[0].value[1])} °C`;
      },
    },
    visualMap: {
      show: false, dimension: 1, seriesIndex: 0,
      pieces: [
        { lt: -0.5, color: cssv("--cool") },
        { gte: -0.5, lt: 0.5, color: ink3 },
        { gte: 0.5, lt: 1.5, color: "#e8a05c" },
        { gte: 1.5, lt: 2.5, color: "#d9502b" },
        { gte: 2.5, color: cssv("--accent") },
      ],
    },
    xAxis: {
      type: "time",
      max: oniPointDate(enso.oni.at(-1)).getTime() + 2.5 * 365 * 864e5,
      axisLine: { lineStyle: { color: line } },
      axisLabel: { color: ink3, fontSize: 10, formatter: (v) => `${new Date(v).getFullYear()}` },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value", min: -3, max: 3, interval: 1,
      splitLine: { lineStyle: { color: line2 } },
      axisLabel: { color: ink3, fontSize: 10, formatter: (v) => (v === 0 ? "0" : `${v > 0 ? "+" : "−"}${Math.abs(v)}`) },
    },
    dataZoom: [
      { type: "inside", filterMode: "none" },
      { type: "slider", height: 16, bottom: 10, borderColor: line, fillerColor: "rgba(179,38,30,.08)",
        handleStyle: { color: ink3 }, textStyle: { color: ink3, fontSize: 9 },
        labelFormatter: (v) => `${new Date(v).getFullYear()}` },
    ],
    series: [{
      type: "line", data, showSymbol: false, lineStyle: { width: 1.3, color: cssv("--ink-2") },
      areaStyle: { opacity: 0.1, color: ink3 },
      markArea: { silent: true, data: markAreas },
      markLine: { silent: true, symbol: "none", lineStyle: { color: line, width: 1 }, data: [{ yAxis: 0 }], label: { show: false } },
    }],
  }, true);

  $("#note-history").textContent = isOni
    ? `ONI, ${enso.oni.length} temporadas desde 1950. ${enso.lag_note}`
    : `Niño 1+2 mensual (ERSSTv5): ${enso.monthly.length} meses desde 1950. Último dato: ${monthLabel(`${enso.latest_month.y}-${String(enso.latest_month.m).padStart(2, "0")}`)}.`;
}

const COMPARE_COLORS = ["#8b93a1", "#1f5f8b", "#2f6b4f", "#8a5a00", "#b3261e"];

function renderCompare(enso) {
  const el = $("#chart-compare");
  if (!el) return;
  if (Charts.compare) Charts.compare.dispose();
  const chart = echarts.init(el, null, { renderer: "canvas" });
  Charts.compare = chart;

  const ink3 = cssv("--ink-3"), line = cssv("--line"), line2 = cssv("--line-2");
  const notable = enso.oni_episodes.filter((e) => e.peak >= 1.5 || e.ongoing)
    .sort((a, b) => a.start.localeCompare(b.start)).slice(-5);

  const series = notable.map((e, i) => {
    const cur = e.ongoing;
    return {
      name: cur ? `${epName(e)} (en curso)` : epName(e),
      type: "line", data: e.series.map((s) => [s.t, s.v]), showSymbol: false,
      lineStyle: { width: cur ? 3.2 : 1.5, color: cur ? cssv("--accent") : COMPARE_COLORS[i], opacity: cur ? 1 : 0.75 },
      itemStyle: { color: cur ? cssv("--accent") : COMPARE_COLORS[i] },
      emphasis: { focus: "series" }, z: cur ? 10 : 2,
      endLabel: { show: true, color: cur ? cssv("--accent") : ink3, fontSize: 10, fontWeight: cur ? 700 : 400,
        formatter: (p) => p.seriesName, distance: 4 },
    };
  });

  chart.setOption({
    ...chartBase(),
    grid: { left: 40, right: 78, top: 26, bottom: 36 },
    tooltip: {
      trigger: "axis", valueFormatter: (v) => `${signed(v)} °C`,
      axisPointer: { type: "line", lineStyle: { color: ink3 } },
      backgroundColor: cssv("--surface"), borderColor: line, textStyle: { color: cssv("--ink") },
    },
    xAxis: {
      type: "value", min: 0, max: Math.max(...notable.map((e) => e.series.length), 12) + 2,
      name: "temporadas desde el inicio", nameLocation: "middle", nameGap: 24,
      nameTextStyle: { color: ink3, fontSize: 10 },
      axisLabel: { color: ink3, fontSize: 10 }, splitLine: { lineStyle: { color: line2 } },
    },
    yAxis: {
      type: "value", min: 0, splitLine: { lineStyle: { color: line2 } },
      axisLabel: { color: ink3, fontSize: 10 },
    },
    series,
  }, true);

  const cur = enso.oni_current;
  if (cur) {
    const cmp = enso.oni_episodes.filter((e) => !e.ongoing && e.series.length >= cur.seasons)
      .sort((a, b) => b.peak - a.peak)[0];
    const faster = cmp ? cur.peak > cmp.series[cur.seasons - 1]?.v : null;
    $("#compare-badge").textContent = cmp
      ? (faster ? `Más intenso que ${epName(cmp)} en este punto` : `Menos intenso que ${epName(cmp)} en este punto`)
      : "Episodio en curso";
  }
}

function renderAllCharts(enso, enfen, mode) {
  renderIndicesChart(enfen);
  renderHistory(enso, mode || "oni");
  renderCompare(enso);
}

/* ======================================================================
   Tablas y bloques
   ====================================================================== */

function renderEpisodesTable(enso) {
  const rows = enso.oni_episodes.filter((e) => e.peak >= 1.5 || e.ongoing).sort((a, b) => b.peak - a.peak);
  $("#table-episodes tbody").innerHTML = rows.map((e) => `
    <tr${e.ongoing ? ' style="font-weight:650"' : ""}>
      <td>${epName(e)}${e.ongoing ? ' <span class="tag tag-warm3">en curso</span>' : ""}</td>
      <td class="num">${e.seasons} trim.</td>
      <td class="num">${signed(e.peak)}</td>
      <td>${e.peak_label}</td>
    </tr>`).join("");
}

function renderWeekly(enfen) {
  const rows = enfen.weekly?.rows || [];
  const tb = document.querySelector("#table-weekly tbody");
  if (!tb) return;
  tb.innerHTML = rows.map((r) => `
    <tr>
      <td>${dateLabel(r.date).replace(/ de \d{4}$/, "")}</td>
      <td class="num">${nf(1).format(r.n12)}</td>
      <td class="num">${tag(signed(r.n12a, 1), "tag-warm3")}</td>
      <td class="num">${nf(1).format(r.n34)}</td>
      <td class="num">${tag(signed(r.n34a, 1), "tag-warm2")}</td>
    </tr>`).join("");
}

function renderIndicesTable(enfen) {
  $("#table-indices tbody").innerHTML = [...enfen.indices].reverse().map((r) => `
    <tr${r.provisional ? ' style="font-style:italic"' : ""}>
      <td>${monthLabel(r.month)}${r.provisional ? " *" : ""}</td>
      <td class="num">${signed(r.icen)} ${tag(r.icen_cat.replace("Cálida ", ""), catClass(r.icen_cat))}</td>
      <td class="num">${signed(r.roni)}</td>
      <td class="num">${signed(r.oni)}</td>
    </tr>`).join("");
}

function renderForecast(enfen) {
  $("#forecast").innerHTML = enfen.forecast.map((f) => `
    <div class="card fc-card">
      <p class="fc-region">${f.region}</p>
      <p class="fc-mag">${f.event}: <span>${f.magnitude.toLowerCase()}</span></p>
      <p class="fc-detail">Hasta ${monthLabel(f.until, true)}. Luego, ${f.then.toLowerCase()}.</p>
    </div>`).join("");

  const startY = 2026, startM = 9;
  const months = Array.from({ length: 15 }, (_, i) => new Date(startY, startM + i, 1));
  const pct = (iso) => {
    const [y, m] = iso.split("-").map(Number);
    const v = (new Date(y, m, 1) - months[0]) / (months.at(-1) - months[0]);
    return Math.max(2, Math.min(100, v * 100));
  };
  const bars = enfen.forecast.map((f, i) => `
    <div class="tl-row">
      <div class="tl-label">${f.region}</div>
      <div class="tl-track"><div class="tl-bar${i ? " soft" : ""}" style="left:0;width:${pct(f.until)}%"></div></div>
    </div>`).join("");
  const labels = months.filter((d, i) => i % 3 === 0 || i === months.length - 1)
    .map((d) => `<span>${MONTH_ES[d.getMonth()]} ${String(d.getFullYear()).slice(2)}</span>`).join("");
  $("#timeline").innerHTML = `${bars}<div class="tl-months"><div></div><div>${labels}</div></div>`;
}

function renderTerritory(agua) {
  const t = agua.territory || {};
  $("#territory-summary").textContent = t.summary || "";

  // --- fichas
  if (t.titicaca) {
    $("#titicaca-value").textContent = t.titicaca.value;
    $("#titicaca-text").innerHTML = `${t.titicaca.detail} <span class="cite">p. ${t.titicaca.page}</span>`;
  }
  if (t.lluvias) {
    $("#lluvias-value").textContent = t.lluvias.value;
    $("#lluvias-text").innerHTML = `${t.lluvias.detail} <span class="cite">pp. ${t.lluvias.page} y ${t.lluvias.page_forecast}</span>`;
  }

  const ink3 = cssv("--ink-3"), line2 = cssv("--line-2"), accent = cssv("--accent"), cool = cssv("--cool");
  const accentSoft = cssv("--accent-soft"), coolSoft = cssv("--cool-soft");

  // --- ríos destacados
  const destacados = t.rios_destacados || [];
  const rios = (agua.rios || []).filter((r) => destacados.includes(r.rio) && r.oct_anom !== null);
  rios.sort((x, y) => x.oct_anom - y.oct_anom);

  const elR = $("#chart-rios");
  if (elR) {
    (Charts.rios ||= echarts.init(elR)).dispose();
    const cr = echarts.init(elR, null, { renderer: "canvas" });
    Charts.rios = cr;
    cr.setOption({
      ...chartBase(),
      grid: { left: 8, right: 62, top: 8, bottom: 24, containLabel: true },
      tooltip: {
        trigger: "axis", axisPointer: { type: "shadow" },
        backgroundColor: cssv("--surface"), borderColor: cssv("--line"), textStyle: { color: cssv("--ink") },
        formatter: (p) => `${p[0].name}<br>${signed(p[0].value, 1)} % vs. normal`,
      },
      xAxis: {
        type: "value", axisLabel: { color: ink3, fontSize: 10, formatter: "{value}%" },
        splitLine: { lineStyle: { color: line2 } },
      },
      yAxis: {
        type: "category", data: rios.map((r) => r.rio.replace(" (", " · ").replace(")", "")),
        axisLabel: { color: ink3, fontSize: 10 }, axisTick: { show: false },
        axisLine: { lineStyle: { color: line2 } },
      },
      series: [{
        type: "bar", barMaxWidth: 13,
        data: rios.map((r) => ({
          value: r.oct_anom,
          itemStyle: { color: r.oct_anom >= 0 ? accent : cool, opacity: 0.85, borderRadius: 2 },
        })),
        label: {
          show: true, position: "right", color: ink3, fontSize: 9.5,
          formatter: (p) => `${p.value > 0 ? "+" : ""}${nf(0).format(p.value)}%`,
        },
        markLine: {
          silent: true, symbol: "none", label: { show: false },
          lineStyle: { color: ink3, width: 1 }, data: [{ xAxis: 0 }],
        },
      }],
    }, true);
  }

  // --- reservorios
  const res = [...(agua.reservorios || [])].sort((x, y) => x.pct_util - y.pct_util);
  $("#reservorios-sub").textContent = `${res.length} embalses. Promedio nacional: 58 % de la capacidad útil.`;

  const elRe = $("#chart-reservorios");
  if (elRe) {
    (Charts.reservorios ||= echarts.init(elRe)).dispose();
    const ce = echarts.init(elRe, null, { renderer: "canvas" });
    Charts.reservorios = ce;
    ce.setOption({
      ...chartBase(),
      grid: { left: 8, right: 46, top: 8, bottom: 24, containLabel: true },
      tooltip: {
        trigger: "axis", axisPointer: { type: "shadow" },
        backgroundColor: cssv("--surface"), borderColor: cssv("--line"), textStyle: { color: cssv("--ink") },
        formatter: (p) => {
          const r = res[p[0].dataIndex];
          return `<strong>${r.reservorio}</strong><br>${r.pct_util} % útil · ${r.departamento}<br>${nf(1).format(r.almacenado_hm3)} de ${nf(1).format(r.capacidad_hm3)} hm³`;
        },
      },
      xAxis: { type: "value", max: 100, axisLabel: { color: ink3, fontSize: 10, formatter: "{value}%" }, splitLine: { lineStyle: { color: line2 } } },
      yAxis: {
        type: "category", data: res.map((r) => r.reservorio),
        axisLabel: { color: ink3, fontSize: 9.5 }, axisTick: { show: false }, axisLine: { lineStyle: { color: line2 } },
      },
      series: [{
        type: "bar", barMaxWidth: 11,
        data: res.map((r) => ({
          value: r.pct_util,
          itemStyle: {
            color: r.pct_util < 30 ? accent : r.pct_util < 50 ? "#e8a05c" : cool,
            opacity: 0.85, borderRadius: 2,
          },
        })),
        label: { show: true, position: "right", color: ink3, fontSize: 9, formatter: (p) => `${nf(0).format(p.value)}%` },
      }],
    }, true);
  }
}

function renderSectores(enfen, agua) {
  // ---- pesca
  const pesca = (enfen.sectors || []).find((s) => s.id === "pesca");
  const d = pesca?.datos;
  if (d) {
    $("#pesca-stats").innerHTML = `
      <div class="pesca-stat"><div class="v">${nf(0).format(d.cuota_t)}</div><div class="l">cuota ${d.region.toLowerCase()} (t)</div></div>
      <div class="pesca-stat"><div class="v">${nf(0).format(d.desembarque_t)}</div><div class="l">desembarcado (t)</div></div>
      <div class="pesca-stat"><div class="v">${nf(1).format(d.avance_pct)}%</div><div class="l">avance de cuota</div></div>`;
    $("#pesca-bar").style.width = `${Math.max(1.5, d.avance_pct)}%`;
    $("#pesca-note").innerHTML =
      `Temporada ${dateLabel(d.temporada.inicio)} – ${dateLabel(d.temporada.fin)}. Cifras al 12 de octubre de 2026. ` +
      `<span class="cite">ENFEN, p. 15</span>`;
    $("#pesca-list").innerHTML = `
      <li>Temporada norte-centro cerrada desde el ${dateLabel(d.cierre_norte_centro.fecha)} <span class="cite">${d.cierre_norte_centro.rm}</span></li>
      <li>Productividad marina: ${d.clorofila.toLowerCase()} <span class="cite">p. 15</span></li>`;

    const ini = new Date(d.temporada.inicio + "T00:00:00");
    const fin = new Date(d.temporada.fin + "T00:00:00");
    const hoy = new Date();
    const pct = Math.max(0, Math.min(100, ((hoy - ini) / (fin - ini)) * 100));
    $("#pesca-season").innerHTML = `
      <div class="season-track"><div class="season-fill" style="width:${pct.toFixed(1)}%"></div>
        <div class="season-mark" style="left:${pct.toFixed(1)}%"></div></div>
      <div class="season-labels"><span>${dateLabel(d.temporada.inicio).replace(/ de \d{4}$/, "")}</span>
        <span>hoy</span><span>${dateLabel(d.temporada.fin).replace(/ de \d{4}$/, "")}</span></div>`;
  }

  // ---- agro: reservorios de riego
  const nombres = new Set(enfen.territory?.riego_reservorios || []);
  const res = (agua.reservorios || []).filter((r) => nombres.has(r.reservorio))
    .sort((a, b) => a.pct_util - b.pct_util);
  const el = $("#chart-agro");
  if (el) {
    if (Charts.agro) Charts.agro.dispose();
    const c = echarts.init(el, null, { renderer: "canvas" });
    Charts.agro = c;
    const ink3 = cssv("--ink-3"), line2 = cssv("--line-2");
    c.setOption({
      ...chartBase(),
      grid: { left: 8, right: 54, top: 10, bottom: 22, containLabel: true },
      tooltip: {
        trigger: "axis", axisPointer: { type: "shadow" },
        backgroundColor: cssv("--surface"), borderColor: cssv("--line"), textStyle: { color: cssv("--ink") },
        formatter: (p) => {
          const r = res[p[0].dataIndex];
          return `<strong>${r.reservorio}</strong><br>${r.pct_util} % útil · ${r.departamento}<br>${nf(1).format(r.almacenado_hm3)} de ${nf(1).format(r.capacidad_hm3)} hm³`;
        },
      },
      xAxis: { type: "value", max: 100, axisLabel: { color: ink3, fontSize: 10, formatter: "{value}%" }, splitLine: { lineStyle: { color: line2 } } },
      yAxis: { type: "category", data: res.map((r) => r.reservorio), axisLabel: { color: ink3, fontSize: 10 }, axisTick: { show: false }, axisLine: { lineStyle: { color: line2 } } },
      series: [{
        type: "bar", barMaxWidth: 16,
        data: res.map((r) => ({
          value: r.pct_util,
          itemStyle: { color: r.pct_util < 30 ? cssv("--accent") : r.pct_util < 50 ? "#e8a05c" : cssv("--cool"), opacity: .85, borderRadius: 2 },
        })),
        label: { show: true, position: "right", color: ink3, fontSize: 9.5, formatter: (p) => `${nf(0).format(p.value)}%` },
      }],
    }, true);
    $("#agro-note").innerHTML =
      `Reservorios que riegan la costa. Tinajones (Lambayeque) en 18,5 % en plena campaña. ` +
      `<span class="cite">ENFEN, Tabla 5</span>`;
  }

  $("#roadmap").innerHTML = `
    <ul>
      <li><strong>Producción agrícola y precios mayoristas</strong> — MIDAGRI (SIEA y SISAP). El portal SISAP tiene el certificado vencido.</li>
      <li><strong>Desembarques y cuotas por temporada</strong> — PRODUCE / IMARPE, publicados por resolución.</li>
      <li><strong>PBI agropecuario y pesquero, inflación de alimentos</strong> — BCRP (su API bloquea clientes automatizados).</li>
      <li><strong>Hectáreas perdidas y damnificados</strong> — INDECI/SINPAD, que ya alimenta el mapa de incidencias.</li>
    </ul>`;
}

function renderDocuments(enfen) {
  const fmtDay = (iso) => {
    if (!iso) return "";
    const [y, m, d] = iso.split("-").map(Number);
    return `${d} ${MONTH_ES[m - 1]} ${y}`;
  };
  const row = (d, meta, prov) => `
    <a class="doc" href="${d.url}" target="_blank" rel="noopener">
      <span class="doc-title">${d.title}</span>
      <span class="doc-meta">${meta}${prov ? ' <span class="tag tag-warm3">último</span>' : ""}</span>
    </a>`;

  const com = (enfen.comunicados || []).slice(0, 5);
  const inf = (enfen.reports || []).slice(0, 5);
  $("#docs-comunicados").innerHTML = com.length
    ? com.map((d) => row(d, fmtDay(d.cutoff), d === com[0])).join("")
    : `<p class="chart-note">No se pudo leer el sitio del ENFEN.</p>`;
  $("#docs-informes").innerHTML = inf.length
    ? inf.map((d) => row(d, fmtDay(d.cutoff), d === inf[0])).join("")
    : `<p class="chart-note">No se pudo leer el sitio del ENFEN.</p>`;
}

function renderSnippets(share) {
  const labels = ["Alerta costera", "Pacífico central", "Comparación"];
  $("#snippets").innerHTML = share.snippets.map((s, i) => `
    <div class="card snippet">
      <div class="snippet-bar">
        <span class="snippet-id">${labels[i] || `Texto ${i + 1}`} · ${s.length} caracteres</span>
        <button class="btn" type="button" data-copy="${i}">Copiar</button>
      </div>
      <p>${s}</p>
    </div>`).join("");

  $$("#snippets [data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const text = share.snippets[Number(btn.dataset.copy)];
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        const ta = document.createElement("textarea");
        ta.value = text; document.body.appendChild(ta); ta.select();
        document.execCommand("copy"); ta.remove();
      }
      toast("Copiado");
    });
  });
}

function renderSources(meta) {
  const rows = meta.sources.map((s) => {
    const st = s.status || {};
    const what = {
      noaa_nino: "Índices Niño mensuales", noaa_oni: "ONI estacional",
      noaa_sst: "Mapa de temperatura del mar", enfen: "Comunicados e informes",
      indeci: "Emergencias recientes", prensa: "Titulares del día",
    }[s.id] || "";
    return `<tr>
      <td class="src-name"><a href="${s.url}" target="_blank" rel="noopener">${s.name}</a><span class="src-detail">${s.publisher}</span></td>
      <td>${what}</td><td>${s.frequency}</td>
      <td><span class="status-dot ${st.ok ? (st.backup ? "status-backup" : "status-ok") : "status-fail"}">${st.ok ? (st.backup ? "respaldo" : "OK") : "falló"}</span></td>
    </tr>`;
  });
  const c = meta.curated;
  rows.push(`<tr>
    <td class="src-name"><a href="${c.url}" target="_blank" rel="noopener">${c.name}</a><span class="src-detail">${c.document}</span></td>
    <td>Cifras del informe, caudales y embalses</td><td>quincenal</td>
    <td><span class="status-dot status-manual">A mano · ${dateLabel(c.cutoff)}</span></td>
  </tr>`);
  $("#table-sources tbody").innerHTML = rows.join("");
}

/* ======================================================================
   Noticias e incidencias
   ====================================================================== */

const TIPO_COLOR = {
  "Lluvias": "#2a6f9e",
  "Movimiento de tierra": "#8a5a00",
  "Incendio forestal": "#d9502b",
  "Vientos": "#6d7683",
  "Frío": "#4a90d9",
  "Sequía": "#b58b2a",
  "Granizo": "#7fb3d5",
};

function relTime(dateStr) {
  const d = new Date(dateStr);
  if (isNaN(d)) return "";
  const h = (Date.now() - d.getTime()) / 36e5;
  if (h < 1) return "hace minutos";
  if (h < 24) return `hace ${Math.round(h)} h`;
  if (h < 48) return "ayer";
  return `${Math.round(h / 24)} días`;
}

function renderNoticias(data) {
  const el = $("#news-grid");
  if (!el) return;
  if (!data.items?.length) {
    el.innerHTML = `<p class="chart-note">No se encontraron titulares relacionados en la última ejecución.</p>`;
    return;
  }
  el.innerHTML = data.items.map((n) => `
    <a class="card news-card" href="${n.url}" target="_blank" rel="noopener">
      <span class="news-medio">${n.medio}</span>
      <span class="news-title">${n.titulo}</span>
      <span class="news-date">${relTime(n.fecha)}</span>
    </a>`).join("");
}

const ETIQUETA_DANO = {
  personas_damnificadas: ["damnificado", "damnificados"],
  personas_afectadas: ["afectado", "afectados"],
  personas_lesionadas: ["lesionado", "lesionados"],
  personas_fallecidas: ["fallecido", "fallecidos"],
  viviendas_destruidas: ["vivienda destruida", "viviendas destruidas"],
  viviendas_afectadas: ["vivienda afectada", "viviendas afectadas"],
  hectareas_cultivo_afectadas: ["ha de cultivo", "ha de cultivo"],
  hectareas_cultivo_perdidas: ["ha perdida", "ha perdidas"],
  hectareas_cobertura_destruida: ["ha de cobertura", "ha de cobertura"],
};

const danoLabel = (k, v) => {
  const par = ETIQUETA_DANO[k];
  if (!par) return k;
  return v === 1 ? par[0] : par[1];
};

function renderIncidencias(data, danos) {
  const items = data.items || [];
  const porUrl = {};
  (danos?.items || []).forEach((d) => { if (d.metricas && Object.keys(d.metricas).length) porUrl[d.url] = d.metricas; });
  const deps = data.departamentos || [];

  $("#inc-sub").textContent = deps.length
    ? `${items.length} reportes en ${deps.length} departamentos, según el INDECI.`
    : "Sin reportes nuevos en la última consulta.";

  // lista
  $("#inc-list").innerHTML = items.slice(0, 6).map((it) => `
    <a class="inc-item" href="${it.url}" target="_blank" rel="noopener">
      <span class="inc-top"><span class="inc-tipo" style="color:${TIPO_COLOR[it.tipo] || "inherit"}">${it.tipo}</span><span>·</span><span>${relTime(it.fecha)}</span></span>
      <span class="inc-lugar">${it.distrito ? it.distrito + ", " : ""}${it.departamento}</span>
      ${porUrl[it.url] ? `<span class="inc-danos">${Object.entries(porUrl[it.url]).slice(0, 2).map(([k, v]) =>
        `${nf(0).format(v)} ${danoLabel(k, v)}`).join(" · ")}</span>` : ""}
    </a>`).join("") || `<p class="chart-note">Sin datos.</p>`;

  // leyenda
  const tipos = [...new Set(items.map((i) => i.tipo))];
  $("#inc-legend").innerHTML = tipos.map((t) =>
    `<span><i style="background:${TIPO_COLOR[t] || "#888"}"></i>${t}</span>`).join("");

  // mapa
  const el = $("#map-inc");
  if (!el || !window.L) return;
  if (window.__incMap) { window.__incMap.remove(); window.__incMap = null; }
  el.innerHTML = "";
  const dark = theme() === "dark";
  const map = L.map(el, { zoom: 5, zoomSnap: 0.25, zoomDelta: 0.5, minZoom: 3, maxZoom: 8, zoomControl: true, attributionControl: true, scrollWheelZoom: false });
  window.__incMap = map;
  map.fitBounds([[-18.6, -81.6], [0.6, -68.4]], { padding: [10, 10] });
  L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/${dark ? "World_Dark_Gray_Base" : "World_Light_Gray_Base"}/MapServer/tile/{z}/{y}/{x}`,
    { maxZoom: 8, attribution: "© Esri · OpenStreetMap · INDECI" }).addTo(map);

  deps.forEach((d) => {
    const principal = Object.entries(d.tipos).sort((a, b) => b[1] - a[1])[0][0];
    const color = TIPO_COLOR[principal] || "#888";
    const r = 7 + Math.sqrt(d.total) * 4;
    const m = L.circleMarker([d.lat, d.lon], {
      radius: r, color, weight: 2, fillColor: color, fillOpacity: .55,
    }).addTo(map);
    const detalle = Object.entries(d.tipos).map(([t, n]) => `${n} ${t.toLowerCase()}`).join(" · ");
    m.bindTooltip(`<strong>${d.departamento}</strong><br>${detalle}`, { direction: "top", offset: [0, -4] });
    if (d.ultimo?.url) m.on("click", () => window.open(d.ultimo.url, "_blank", "noopener"));
  });
}

function renderDanos(data) {
  const card = $("#danos-card");
  if (!card || !data) return;
  const t = data.totales || {};
  const ha = (t.hectareas_cultivo_afectadas || 0) + (t.hectareas_cultivo_perdidas || 0);
  const haCab = t.hectareas_cobertura_destruida || 0;

  $("#danos-cobertura").textContent =
    `${data.items.filter((i) => !i.sin_datos).length} de ${data.items.length} reportes traen cifras`;

  const kpis = [
    { l: "Damnificados", v: nf(0).format(t.personas_damnificadas || 0) },
    { l: "Personas afectadas", v: nf(0).format(t.personas_afectadas || 0) },
    { l: "Viviendas destruidas", v: nf(0).format(t.viviendas_destruidas || 0) },
    { l: "Hectáreas de cultivo", v: nf(0).format(ha) },
  ];
  $("#danos-kpis").innerHTML = kpis.map((k) => `
    <div class="danos-kpi"><div class="v">${k.v}</div><div class="l">${k.l}</div></div>`).join("");

  const conDatos = (data.por_departamento || []).some((d) =>
    (d.personas_damnificadas || 0) + (d.personas_afectadas || 0) + (d.viviendas_destruidas || 0) +
    (d.hectareas_cultivo_afectadas || 0) + (d.hectareas_cobertura_destruida || 0) > 0);

  if (!conDatos) {
    $("#danos-cobertura").textContent = "sin cifras verificables";
    $("#danos-kpis").innerHTML = "";
    document.querySelector("#danos-card .table-wrap").style.display = "none";
    $("#danos-note").innerHTML =
      `Los ${data.items.length} reportes de esta hora traen la tabla de daños incompleta o con celdas fusionadas, ` +
      `y el INDECI indica que el EDAN sigue en proceso. No se publican estimaciones. ` +
      `Cuando el reporte trae la tabla completa, las cifras aparecen aquí automáticamente.`;
    return;
  }

  const filas = (data.por_departamento || []).filter((d) =>
    (d.personas_damnificadas || 0) + (d.personas_afectadas || 0) + (d.viviendas_destruidas || 0) +
    (d.hectareas_cultivo_afectadas || 0) + (d.hectareas_cobertura_destruida || 0) > 0);
  const sinEdan = (data.por_departamento || []).length - filas.length;
  $("#table-danos tbody").innerHTML = filas.map((d) => {
    const haDep = (d.hectareas_cultivo_afectadas || 0) + (d.hectareas_cultivo_perdidas || 0);
    return `<tr>
      <td>${d.departamento}</td>
      <td class="num">${d.eventos}</td>
      <td class="num">${nf(0).format(d.personas_damnificadas || 0)}</td>
      <td class="num">${nf(0).format(d.personas_afectadas || 0)}</td>
      <td class="num">${nf(0).format(d.viviendas_destruidas || 0)}</td>
      <td class="num">${nf(0).format(haDep)}</td>
      <td class="num">${nf(0).format(d.hectareas_cobertura_destruida || 0)}</td>
    </tr>`;
  }).join("");

  $("#danos-note").innerHTML =
    `Solo las emergencias con Evaluación de Daños (EDAN) enviada al SINPAD traen cifras; ${sinEdan} ` +
    `${sinEdan === 1 ? "departamento" : "departamentos"} ` +
    `con reportes aún no la tienen. Hectáreas de cobertura: ${nf(0).format(haCab)} (forestal y natural). ` +
    `Fuente: INDECI, tablas 3.1 de cada reporte.`;
}

function renderPronostico(data) {
  const el = $("#forecast-ciudades");
  if (!el) return;
  const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
  if (!data?.ciudades?.length) {
    el.innerHTML = `<p class="chart-note">No se pudo obtener el pronóstico.</p>`;
    return;
  }
  el.innerHTML = data.ciudades.map((c) => `
    <div class="card fc-city">
      <h3>${c.ciudad}</h3>
      <div class="fc-days">
        ${c.dias.map((d) => {
          const f = new Date(d.fecha + "T12:00:00");
          const icono = d.lluvia >= 5 ? "🌧" : d.lluvia >= 1 ? "🌦" : d.prob >= 40 ? "☁" : "☀";
          return `<div class="fc-day" title="${d.fecha}">
            <div class="fc-dow">${DIAS[f.getDay()]}</div>
            <div class="fc-icon">${icono}</div>
            <div class="fc-t"><b>${Math.round(d.tmax)}°</b> ${Math.round(d.tmin)}°</div>
            <div class="fc-r">${d.lluvia >= 0.05 ? nf(1).format(d.lluvia) + " mm" : "—"}</div>
          </div>`;
        }).join("")}
      </div>
    </div>`).join("");
}

function renderPesca(pesca) {
  const el = $("#chart-pesca");
  if (!el || !pesca?.mensual?.length) return;
  if (Charts.pesca) Charts.pesca.dispose();
  const c = echarts.init(el, null, { renderer: "canvas" });
  Charts.pesca = c;
  const ink3 = cssv("--ink-3"), line2 = cssv("--line-2"), cool = cssv("--cool"), accent = cssv("--accent");
  const filas = pesca.mensual.slice(-12);
  c.setOption({
    ...chartBase(),
    grid: { left: 44, right: 8, top: 24, bottom: 22 },
    tooltip: {
      trigger: "axis", axisPointer: { type: "shadow" },
      backgroundColor: cssv("--surface"), borderColor: cssv("--line"), textStyle: { color: cssv("--ink") },
      valueFormatter: (v) => `${nf(0).format(v)} t`,
    },
    legend: { show: true, top: 0, right: 0, itemWidth: 9, itemHeight: 9, textStyle: { color: ink3, fontSize: 10 } },
    xAxis: {
      type: "category",
      data: filas.map((m) => {
        const [y, mm] = m.mes.split("-").map(Number);
        return `${MONTH_ES[mm - 1]} ${String(y).slice(2)}`;
      }),
      axisLabel: { color: ink3, fontSize: 9, interval: 1, rotate: 0 }, axisTick: { show: false },
      axisLine: { lineStyle: { color: line2 } },
    },
    yAxis: {
      type: "value", splitLine: { lineStyle: { color: line2 } },
      axisLabel: { color: ink3, fontSize: 9, formatter: (v) => `${Math.round(v / 1000)}k` },
    },
    series: [
      { name: "Norte-Centro", type: "bar", stack: "z", data: filas.map((m) => m["Norte-Centro"]), itemStyle: { color: accent, opacity: .85 } },
      { name: "Sur", type: "bar", stack: "z", data: filas.map((m) => m["Sur"]), itemStyle: { color: cool, opacity: .85 } },
    ],
  }, true);
}

/* ======================================================================
   Utilidades
   ====================================================================== */

function downloadCSV(filename, rows) {
  const csv = rows.map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function bindExports(enfen) {
  $$("[data-export]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.export !== "indices") return;
      downloadCSV("enfen-indices-icen-roni-oni.csv", [
        ["mes", "icen", "categoria_icen", "roni", "categoria_roni", "oni", "categoria_oni", "provisional"],
        ...enfen.indices.map((r) => [r.month, r.icen, r.icen_cat, r.roni, r.roni_cat, r.oni, r.oni_cat, r.provisional ? "si" : "no"]),
      ]);
      toast("CSV descargado");
    });
  });
}

function bindTheme(enso, enfen, state) {
  const btn = $("#theme-toggle");
  const sync = () => {
    btn.setAttribute("aria-label", theme() === "dark" ? "Cambiar a modo claro" : "Cambiar a modo oscuro");
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme() === "dark" ? "#0d1117" : "#fbfaf7");
  };
  sync();
  btn.addEventListener("click", () => {
    const next = theme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("nino-theme", next); } catch (e) {}
    sync();
    renderAllCharts(enso, enfen, state.region);
    MapModule.refreshTheme();
    renderIncidencias(incidencias, danos);
  renderDanos(danos);
  renderPesca(pesca);
  renderPronostico(pronostico);
  });
}

/* ======================================================================
   Init
   ====================================================================== */

/* ======================================================================
   Modo embebido: ?embed=<id-de-seccion>
   ====================================================================== */
function setupEmbed() {
  const id = new URLSearchParams(location.search).get("embed");
  if (!id) return false;
  const target = document.getElementById(id);
  if (!target) return false;
  document.body.classList.add("embed-mode");
  Array.from(document.querySelectorAll("main > *")).forEach((el) => {
    if (el !== target) el.style.display = "none";
  });
  const credit = document.createElement("div");
  credit.className = "embed-credit";
  credit.innerHTML = `<span>Datos: NOAA · ENFEN · INDECI</span>
    <a href="index.html" target="_blank" rel="noopener">El Niño · Perú ↗</a>`;
  document.querySelector("main").appendChild(credit);
  return true;
}

async function init() {
  setupEmbed();
  let enso, enfen, meta, sst, agua, noticias, incidencias, danos, pesca, pronostico;
  try {
    [enso, enfen, meta, sst, agua, noticias, incidencias, danos, pesca, pronostico] = await Promise.all([
      loadJSON("data/enso.json"), loadJSON("data/enfen.json"), loadJSON("data/meta.json"),
      loadJSON("data/sst.json"), loadJSON("data/agua.json"),
      loadJSON("data/noticias.json").catch(() => ({ items: [] })),
      loadJSON("data/incidencias.json").catch(() => ({ items: [], departamentos: [] })),
      loadJSON("data/danos.json").catch(() => null),
      loadJSON("data/pesca.json").catch(() => null),
      loadJSON("data/pronostico.json").catch(() => null),
    ]);
  } catch (err) {
    $("#hero-lede").innerHTML = "<strong>No se pudieron cargar los datos.</strong> Sirve la carpeta por HTTP (por ejemplo <code>python3 -m http.server</code>). Abrir el archivo con <code>file://</code> bloquea las descargas.";
    console.error(err);
    return;
  }

  const state = { region: "oni" };
  renderKPIs(enso, enfen);
  renderIndicesTable(enfen);
  renderWeekly(enfen);
  renderIndicesChart(enfen);
  renderHistory(enso, "oni");
  renderCompare(enso);
  renderEpisodesTable(enso);
  renderForecast(enfen);
  renderTerritory(agua);
  renderSectores(enfen, agua);
  renderNoticias(noticias);
  renderIncidencias(incidencias, danos);
  renderDanos(danos);
  renderPesca(pesca);
  renderPronostico(pronostico);
  renderDocuments(enfen);
  renderSources(meta);
  bindExports(enfen);
  bindTheme(enso, enfen, state);

  const btnMcp = document.querySelector("[data-copy-mcp]");
  if (btnMcp) {
    btnMcp.addEventListener("click", async () => {
      const url = "https://nino-peru-mcp.doctorsudoku.workers.dev/mcp";
      try { await navigator.clipboard.writeText(url); } catch { /* sin permisos */ }
      toast("Endpoint copiado");
    });
  }

  if (window.L && sst?.boxes) {
    MapModule.init(sst);
  } else {
    const card = document.querySelector(".map-card");
    if (card) card.style.display = "none";
    console.warn("Sin datos del mapa; se oculta el bloque.");
  }

  $("#foot-built").textContent = dateLabel(meta.built_at.slice(0, 10));
  $("#foot-next").textContent = dateLabel(enfen.alert?.next_update);
  $("#cite-date").textContent = dateLabel(new Date().toISOString().slice(0, 10));

  $$("[data-region]").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$("[data-region]").forEach((b) => b.setAttribute("aria-pressed", "false"));
      btn.setAttribute("aria-pressed", "true");
      state.region = btn.dataset.region;
      renderHistory(enso, state.region);
    });
  });

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      Charts.indices?.resize();
      Charts.history?.resize();
      Charts.compare?.resize();
      Charts.rios?.resize();
      Charts.reservorios?.resize();
      Charts.agro?.resize();
      Charts.pesca?.resize();
      MapModule.map?.invalidateSize();
    }, 160);
  });
}

document.addEventListener("DOMContentLoaded", init);
