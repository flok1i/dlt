"use strict";
// Seccion Formula 1. Usa las utilidades de app.js (esc, dec, hora, mercado, avisoFuentes, etc.)

const f1 = { datos: null, mercado: "gana" };
const TABS_F1 = [["pilotos", "Pilotos"], ["mercados", "Mercados"], ["sanciones", "Sanciones"], ["mejoras", "Mejoras"], ["circuito", "Circuito"], ["campeonato", "Campeonato"]];
const MERCADOS_F1 = [["gana", "Ganador"], ["podio", "Podio"], ["puntos", "Puntos (top 10)"], ["abandona", "Abandona"], ["duelo", "Le gana al compañero"]];
const TIPO_SANCION = { grilla: "rojo", penalización: "rojo", descalificado: "rojo", reprimenda: "amarillo", advertencia: "amarillo", multa: "amarillo", investigación: "", "sin sanción": "" };

const fechaLarga = (iso) => new Date(iso).toLocaleDateString("es-AR", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" });
const posTxt = (r) => (!r ? "–" : r.pos ? `P${r.pos}` : "DNF");
const clasePos = (r) => (!r ? "" : !r.pos ? "rojo" : r.pos === 1 ? "verde" : r.pos <= 3 ? "amarillo" : "");

function cuentaRegresiva(iso) {
  const min = Math.round((new Date(iso) - Date.now()) / 60000);
  if (min <= 0) return "";
  if (min < 60) return `en ${min} min`;
  const h = Math.floor(min / 60);
  return h < 48 ? `en ${h} h` : `en ${Math.round(h / 24)} días`;
}

function f1Sesiones(gp) {
  const ahora = Date.now();
  const proxima = gp.sesiones.find((s) => new Date(s.fecha) > ahora);
  return `<div class="lista">${gp.sesiones.map((s) => {
    const pasada = new Date(s.fecha) < ahora;
    const esProx = s === proxima;
    return `<div${pasada ? ' style="opacity:.5"' : ""}><span>${s.nombre === "Carrera" ? `<b>${esc(s.nombre)}</b>` : esc(s.nombre)}${esProx ? ` <span class="tag verde">${cuentaRegresiva(s.fecha)}</span>` : ""}</span>
      <span><small>${fechaLarga(s.fecha)}</small> <b>${hora(s.fecha)}</b></span></div>`;
  }).join("")}</div>`;
}

function f1Inicio() {
  const d = f1.datos;
  const gp = d.gp;
  let html = avisoFuentes(d) + lineaActualizado(d);
  html += `<h2 class="dia">Próximo Gran Premio</h2>
  <a class="partido" href="#/f1/gp">
    <div class="p-top"><span class="p-comp">Fórmula 1 · Fecha ${d.ronda} de ${d.total_rondas}</span>${gp.sprint ? '<span class="tag amarillo">Sprint</span>' : ""}</div>
    <div class="gp-nombre">${esc(gp.nombre)}</div>
    <div class="p-info"><span>${esc(gp.circuito)} · ${esc(gp.localidad)}, ${esc(gp.pais)}</span></div>
  </a>
  <section class="seccion"><h3>Horarios <small>hora de Argentina</small></h3>${f1Sesiones(gp)}</section>
  <section class="seccion"><h3>Campeonato <small>tras ${d.campeonato.ronda} fechas</small></h3>
    <div class="lista">${d.campeonato.pilotos.slice(0, 5).map((p) => `<div><span><b>${p.pos}.</b> ${esc(p.nombre)} <small>${esc(p.equipo || "")}</small></span><b>${dec(p.puntos, 0)} pts</b></div>`).join("")}</div>
  </section>
  <p style="padding:0 12px 16px"><a class="boton" href="#/f1/gp">Ver análisis del Gran Premio ›</a></p>`;
  app.innerHTML = html;
}

function f1Cabecera(d) {
  const gp = d.gp;
  const carrera = gp.sesiones.find((s) => s.nombre === "Carrera");
  return `<a class="volver" href="#/f1">‹ Fórmula 1</a>
  <section class="cabecera">
    <div class="cab-comp">Fórmula 1 · Fecha ${d.ronda} de ${d.total_rondas}${gp.sprint ? " · Sprint" : ""}</div>
    <div class="gp-nombre" style="text-align:center;margin:10px 0">${esc(gp.nombre)}</div>
    <div class="cab-datos">
      <span>Circuito: <b>${esc(gp.circuito)}</b> (${esc(gp.localidad)}, ${esc(gp.pais)})</span>
      <span>Carrera: <b>${fechaLarga(carrera.fecha)} ${hora(carrera.fecha)}</b> ${cuentaRegresiva(carrera.fecha) ? `<span class="tag verde">${cuentaRegresiva(carrera.fecha)}</span>` : ""}</span>
    </div>
  </section>`;
}

function f1Pilotos(d) {
  let html = `<p class="nota" style="padding:10px 16px">Temporada ${d.temporada}: ${d.carreras_disputadas} carreras disputadas. Promedio de carrera = solo carreras terminadas.</p>`;
  for (const p of d.pilotos) {
    const dq = p.duelo_quali, dc = p.duelo_carrera;
    html += `<section class="seccion jugador">
      <h3><span>${p.posicion}. ${esc(p.nombre)} <small>${esc(p.equipo || "")}</small></span><span>${dec(p.puntos, 0)} pts</span></h3>
      <div class="grilla-stats">
        <div><small>Clasif. prom.</small><b>${p.prom_quali != null ? `P${dec(p.prom_quali)}` : "–"}</b></div>
        <div><small>Carrera prom.</small><b>${p.prom_carrera != null ? `P${dec(p.prom_carrera)}` : "–"}</b></div>
        <div><small>Victorias</small><b>${p.victorias}</b></div>
        <div><small>Podios</small><b>${p.podios}</b></div>
        <div><small>Abandonos</small><b>${p.abandonos}</b></div>
        <div><small>V. rápidas</small><b>${p.vueltas_rapidas}</b></div>
      </div>
      ${p.companero ? `<p class="nota">vs ${esc(p.companero)}: clasificación <b class="${dq[0] > dq[1] ? "txt-verde" : dq[0] < dq[1] ? "txt-rojo" : ""}">${dq[0]}-${dq[1]}</b> · carrera <b class="${dc[0] > dc[1] ? "txt-verde" : dc[0] < dc[1] ? "txt-rojo" : ""}">${dc[0]}-${dc[1]}</b></p>` : ""}
      <div class="ultimas"><small>Últimas:</small>${p.ultimas.map((r) => `<span class="tag ${clasePos(r)}" title="${esc(r.gp)}">${posTxt(r)}</span>`).join("")}</div>
    </section>`;
  }
  return html;
}

function f1Mercados(d) {
  const m = f1.mercado;
  const nombreM = Object.fromEntries(MERCADOS_F1)[m];
  const filas = [...d.probabilidades].sort((a, b) => b[m] - a[m]);
  let html = `<nav class="chips">${MERCADOS_F1.map(([k, n]) => `<button class="chip ${k === m ? "activo" : ""}" data-mercado="${k}">${n}</button>`).join("")}</nav>
    <p class="nota" style="padding:0 16px 10px">Estimación DLT con las últimas 8 carreras (pesan más las recientes). ${m === "duelo" ? "Duelo: carreras de la temporada en que terminó delante de su compañero." : ""} Es orientativo: en F1 influyen mucho la clasificación y el clima.</p>
    <section class="seccion"><h3>${esc(nombreM)}</h3>`;
  for (const f of filas) {
    if (m !== "duelo" && m !== "abandona" && f[m] < 0.005) continue;
    const nombre = m === "duelo" ? `${f.nombre} termina delante de ${f.companero || "su compañero"}`
      : m === "gana" ? `${f.nombre} gana` : m === "podio" ? `${f.nombre} hace podio`
      : m === "puntos" ? `${f.nombre} suma puntos` : `${f.nombre} abandona`;
    html += mercado(app.dataset.pid, { nombre, prob: f[m] }, `${m}:${f.id}`);
  }
  return html + "</section>";
}

function f1Circuito(d) {
  const c = d.circuito;
  if (!c.anios.length) return '<p class="vacio">No hay historial de este circuito en los últimos años.</p>';
  return `<p class="nota" style="padding:10px 16px">Resultado de cada piloto en ${esc(d.gp.circuito)}. DNF = no terminó. Primero los pilotos de la temporada actual.</p>
  <section class="seccion" style="overflow-x:auto"><table class="tabla compacta">
    <tr><th>Piloto</th>${c.anios.map((a) => `<th class="n">${a}</th>`).join("")}</tr>
    ${c.pilotos.map((p) => `<tr${p.actual ? "" : ' style="opacity:.55"'}><td>${esc(p.nombre)}</td>${c.anios.map((a) => {
      const r = p.resultados[a];
      return `<td class="n"><span class="tag ${clasePos(r)}" ${r ? `title="${esc(r.equipo)} · largó P${r.grid ?? "?"}"` : ""}>${posTxt(r)}</span></td>`;
    }).join("")}</tr>`).join("")}
  </table></section>`;
}

function f1Campeonato(d) {
  const c = d.campeonato;
  return `<section class="seccion"><h3>Pilotos <small>tras ${c.ronda} fechas</small></h3>
    <table class="tabla"><tr><th>#</th><th>Piloto</th><th class="n">Vic.</th><th class="n">Pts</th></tr>
    ${c.pilotos.map((p) => `<tr><td>${p.pos}</td><td>${esc(p.nombre)}<br><small class="sec">${esc(p.equipo || "")}</small></td><td class="n">${p.victorias}</td><td class="n">${dec(p.puntos, 0)}</td></tr>`).join("")}
    </table></section>
  <section class="seccion"><h3>Constructores</h3>
    <table class="tabla"><tr><th>#</th><th>Equipo</th><th class="n">Vic.</th><th class="n">Pts</th></tr>
    ${c.constructores.map((e) => `<tr><td>${e.pos}</td><td>${esc(e.nombre)}</td><td class="n">${e.victorias}</td><td class="n">${dec(e.puntos, 0)}</td></tr>`).join("")}
    </table></section>`;
}

function f1Sanciones(d) {
  const fia = d.fia;
  const conSancion = (fia?.sanciones || []).filter((s) => s.tipo !== "sin sanción");
  const sinSancion = (fia?.sanciones || []).filter((s) => s.tipo === "sin sanción");
  let html = "";
  if (fia) {
    html += `<p class="nota" style="padding:10px 16px">Decisiones de los comisarios publicadas por la FIA para el <b>${esc(fia.evento || "último Gran Premio")}</b>. Las marcadas "afecta a este GP" se cumplen en la próxima carrera.</p>`;
    html += `<section class="seccion"><h3>Sanciones <small>${conSancion.length}</small></h3><div class="lista">${conSancion.length ? conSancion.map((s) => `
      <div style="align-items:flex-start"><span><b>${esc(s.piloto || "–")}</b> ${s.proxima_carrera ? '<span class="tag rojo">afecta a este GP</span>' : ""}<br>${esc(s.decision_es || s.decision || "")}<br>
        <small>${esc(s.sesion || "")}${s.hecho ? ` · <span class="ingles">${esc(s.hecho.slice(0, 140))}</span>` : ""}</small><br>
        <small><a href="${esc(s.url)}" target="_blank" rel="noopener" style="color:var(--acento)">Documento FIA ›</a></small></span>
        <span class="tag ${TIPO_SANCION[s.tipo] ?? ""}">${esc(s.tipo)}</span></div>`).join("") : "<div><small>Sin sanciones</small></div>"}</div>
      ${sinSancion.length ? `<details><summary>Investigados sin sanción (${sinSancion.length})</summary><div class="lista">${sinSancion.map((s) => `<div><span>${esc(s.piloto || "–")} <small>· ${esc(s.sesion || "")}</small></span><small>${esc(s.titulo.replace(/^Doc \d+ - /, ""))}</small></div>`).join("")}</div></details>` : ""}
    </section>`;
  } else {
    html += '<div class="aviso">No se pudieron leer los documentos de la FIA. Se muestran solo los mensajes de carrera de OpenF1.</div>';
  }
  const msgs = d.sanciones || [];
  html += `<section class="seccion"><h3>Mensajes de carrera <small>OpenF1</small></h3>
    <p class="nota">Lo que anuncian los comisarios por radio durante las sesiones (se publica al terminar cada sesión).</p>
    <div class="lista">${msgs.length ? msgs.map((s) => `<div style="align-items:flex-start"><span>${s.piloto ? `<b>${esc(s.piloto)}</b><br>` : ""}<small class="ingles">${esc(s.texto)}</small><br><small>${esc(s.gp || "")} · ${esc(s.sesion)}${s.fecha ? ` · ${fechaLarga(s.fecha)} ${hora(s.fecha)}` : ""}</small></span><span class="tag ${TIPO_SANCION[s.tipo] ?? ""}">${esc(s.tipo)}</span></div>`).join("") : "<div><small>Sin mensajes por ahora</small></div>"}</div>
  </section>`;
  return html;
}

function f1Mejoras(d) {
  const m = d.fia?.mejoras;
  if (!m) return '<p class="vacio">La FIA todavía no publicó las mejoras de este Gran Premio. Suelen salir el jueves.</p>';
  const con = m.equipos.filter((e) => e.mejoras.length);
  const sin = m.equipos.filter((e) => !e.mejoras.length && e.leido);
  const noLeidos = m.equipos.filter((e) => !e.leido);
  let html = `<p class="nota" style="padding:10px 16px">Piezas nuevas que declaró cada equipo para el <b>${esc(d.fia.evento || "Gran Premio")}</b> (documento de la FIA del ${esc(m.publicado)}). Lectura automática del PDF: ante la duda, revisá el <a href="${esc(m.url)}" target="_blank" rel="noopener" style="color:var(--acento)">documento original</a>.</p>`;
  for (const e of con) {
    html += `<section class="seccion"><h3>${esc(e.equipo)} <small>${e.mejoras.length} ${e.mejoras.length === 1 ? "mejora" : "mejoras"}</small></h3>
      <div class="lista">${e.mejoras.map((x) => `<div style="align-items:flex-start"><span><b>${esc(x.componente)}</b><br><small>${esc(x.motivo)}</small><br><small class="ingles">${esc(x.detalle)}</small></span></div>`).join("")}</div></section>`;
  }
  if (noLeidos.length) html += `<div class="aviso">No se pudo leer el detalle de: ${esc(noLeidos.map((e) => e.equipo).join(", "))}. Miralo en el documento original.</div>`;
  if (sin.length) html += `<section class="seccion"><h3>Sin mejoras</h3><p class="nota">${esc(sin.map((e) => e.equipo).join(" · "))}</p></section>`;
  return html;
}

function f1Gp(tab) {
  const d = f1.datos;
  app.dataset.pid = `f1-${d.temporada}-${d.ronda}`;
  tab = TABS_F1.some(([k]) => k === tab) ? tab : "pilotos";
  const cuerpo = tab === "mercados" ? f1Mercados(d) : tab === "circuito" ? f1Circuito(d) : tab === "campeonato" ? f1Campeonato(d)
    : tab === "sanciones" ? f1Sanciones(d) : tab === "mejoras" ? f1Mejoras(d) : f1Pilotos(d);
  const nSanc = (d.fia?.sanciones || []).filter((s) => s.proxima_carrera).length;
  app.innerHTML = f1Cabecera(d)
    + `<nav class="tabs">${TABS_F1.map(([k, n]) => `<a class="tab ${k === tab ? "activo" : ""}" href="#/f1/gp/${k}">${n}${k === "sanciones" && nSanc ? ` (${nSanc})` : ""}</a>`).join("")}</nav>`
    + cuerpo;
  app.querySelectorAll("[data-mercado]").forEach((b) => b.addEventListener("click", () => {
    f1.mercado = b.dataset.mercado;
    f1Gp("mercados");
  }));
}

async function vistaF1(ruta, tab) {
  if (!f1.datos) {
    try { f1.datos = await cargar("data/f1/gp.json"); }
    catch (e) { app.innerHTML = errorCarga(); return; }
  }
  if (!f1.datos.gp) { app.innerHTML = avisoFuentes(f1.datos) + '<p class="vacio">Todavía no hay datos de Fórmula 1.</p>'; return; }
  if (ruta === "gp") f1Gp(tab);
  else { delete app.dataset.pid; f1Inicio(); }
}
