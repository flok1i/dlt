"use strict";
// Seccion NBA. Usa las utilidades de app.js (esc, dec, hora, mercado, avisoFuentes, etc.)

const nba = { indice: null, partidos: {}, lado: "local" };
const TABS_NBA = [["jugadores", "Jugadores"], ["equipos", "Equipos"], ["bajas", "Bajas"], ["historial", "Historial"]];
const ESTADO_BAJA = { Descartado: "rojo", Dudoso: "amarillo", Descansa: "" };
const COLS_NBA = [["min", "MIN"], ["pts", "PTS"], ["reb", "REB"], ["ast", "AST"], ["tpm", "3PT"], ["stl", "ROB"], ["blk", "TAP"]];

function nbaInicio() {
  const idx = nba.indice;
  let html = avisoFuentes(idx) + lineaActualizado(idx);
  if (!idx.partidos.length) {
    html += '<p class="vacio">No hay partidos de NBA hoy ni en los próximos dos días.<br>La temporada regular 2026-27 arranca el 20 de octubre.</p>';
  }
  let diaActual = null;
  for (const p of idx.partidos) {
    const d = nombreDia(p.fecha);
    if (d !== diaActual) { html += `<h2 class="dia">${esc(d)}</h2>`; diaActual = d; }
    html += `
    <a class="partido" href="#/nba/p/${p.id}">
      <div class="p-top"><span class="p-comp">NBA</span>
        <span class="p-hora">${p.estado === "in" ? '<span class="tag rojo">EN JUEGO</span>' : hora(p.fecha)}</span></div>
      <div class="p-equipos">
        <div class="eq">${escudo(p.visita.logo)}${esc(p.visita.nombre)}</div>
        <div class="eq">${escudo(p.local.logo)}${esc(p.local.nombre)} <small class="sec">(local)</small></div>
      </div>
      <div class="p-info">
        ${p.total_esperado != null ? `<span>Total esperado: <b>${dec(p.total_esperado)}</b> pts</span>` : ""}
      </div>
      <div class="p-info">
        ${p.bajas ? `<span class="tag rojo">${p.bajas} ${p.bajas === 1 ? "baja" : "bajas"}</span>` : ""}
        ${p.dudosos ? `<span class="tag amarillo">${p.dudosos} ${p.dudosos === 1 ? "dudoso" : "dudosos"}</span>` : ""}
      </div>
    </a>`;
  }
  app.innerHTML = html;
}

function nbaCabecera(d) {
  return `
  <a class="volver" href="#/nba">‹ Partidos NBA</a>
  <section class="cabecera">
    <div class="cab-comp">NBA · Temporada ${d.temporada - 1}-${String(d.temporada).slice(2)}</div>
    <div class="cab-equipos">
      <div class="cab-eq">${escudo(d.visita.logo)}${esc(d.visita.nombre)}</div>
      <div class="cab-hora"><b>${hora(d.fecha)}</b><span>${esc(nombreDia(d.fecha))}</span></div>
      <div class="cab-eq">${escudo(d.local.logo)}${esc(d.local.nombre)}</div>
    </div>
    <div class="cab-datos"><span>Estadio: <b>${esc(d.estadio || "–")}</b> (local: ${esc(d.local.nombre)})</span></div>
  </section>`;
}

function nbaJugadores(d, pid) {
  const lado = nba.lado;
  const lista = d.jugadores[lado] || [];
  let html = `<div class="selector">
    <button data-lado="visita" class="${lado === "visita" ? "activo" : ""}">${escudo(d.visita.logo, "escudo")}${esc(d.visita.nombre)}</button>
    <button data-lado="local" class="${lado === "local" ? "activo" : ""}">${escudo(d.local.logo, "escudo")}${esc(d.local.nombre)}</button>
  </div>`;
  if (!lista.length) return html + '<p class="vacio">Sin datos de jugadores.</p>';
  const base = lista[0].base;
  html += `<p class="nota" style="padding:10px 16px">Promedios ${base === "temporada" ? "de la temporada" : "de la temporada pasada (la actual todavía tiene pocos partidos)"} y de los últimos 5 partidos. Las líneas usan 60% temporada + 40% últimos 5.</p>`;
  for (const j of lista) {
    const tags = [
      j.baja ? `<span class="tag ${ESTADO_BAJA[j.baja] || ""}">${esc(j.baja)}</span>` : "",
      j.pocos_datos ? '<span class="tag amarillo">Pocos datos</span>' : "",
    ].join("");
    html += `<section class="seccion jugador">
      <h3><span>${esc(j.nombre)} <small>${esc(j.pos || "")} · ${j.n} PJ</small></span><span>${tags}</span></h3>
      <table class="tabla compacta">
        <tr><th></th>${COLS_NBA.map(([, n]) => `<th class="n">${n}</th>`).join("")}</tr>
        <tr><td>${j.base === "temporada" ? "Temp." : "Temp. ant."}</td>${COLS_NBA.map(([k]) => `<td class="n">${dec(j.prom[k])}</td>`).join("")}</tr>
        <tr><td>${j.base === "temporada" ? "Últ. 5" : "Últ. 5 (ant.)"}</td>${COLS_NBA.map(([k]) => `<td class="n">${dec(j.prom5[k])}</td>`).join("")}</tr>
      </table>
      <div class="mini">${j.mercados.map((m) => `<div><span>${esc(m.nombre)}</span><span class="barra"><i style="width:${Math.round(m.prob * 100)}%"></i></span><b>${pct(m.prob)}</b></div>`).join("")}</div>
      <details><summary>Comparar cuotas</summary>
        ${j.mercados.map((m) => mercado(pid, { nombre: `${j.nombre}, ${m.nombre.toLowerCase()}`, prob: m.prob }, `j${j.id}:${m.nombre}`)).join("")}
      </details>
    </section>`;
  }
  return html;
}

function nbaEquipos(d, pid) {
  const e = d.equipos;
  if (!e) return '<p class="vacio">No hay datos suficientes de los equipos.</p>';
  const pr = e.promedios;
  let html = e.pocos_datos ? '<div class="aviso">Pocos datos: los porcentajes pueden variar bastante.</div>' : "";
  html += `<section class="seccion"><h3>Puntos <small>${esc(pr.local.base)}</small></h3>
    <table class="tabla">
      <tr><th>Promedio</th><th class="n">A favor</th><th class="n">En contra</th><th class="n">PJ</th></tr>
      <tr><td>${esc(d.local.nombre)} (local)</td><td class="n">${dec(pr.local.local.favor)}</td><td class="n">${dec(pr.local.local.contra)}</td><td class="n">${pr.local.local.n}</td></tr>
      <tr><td>${esc(d.local.nombre)} (visitante)</td><td class="n">${dec(pr.local.visita.favor)}</td><td class="n">${dec(pr.local.visita.contra)}</td><td class="n">${pr.local.visita.n}</td></tr>
      <tr><td>${esc(d.visita.nombre)} (local)</td><td class="n">${dec(pr.visita.local.favor)}</td><td class="n">${dec(pr.visita.local.contra)}</td><td class="n">${pr.visita.local.n}</td></tr>
      <tr><td>${esc(d.visita.nombre)} (visitante)</td><td class="n">${dec(pr.visita.visita.favor)}</td><td class="n">${dec(pr.visita.visita.contra)}</td><td class="n">${pr.visita.visita.n}</td></tr>
    </table>
    <p class="nota">Esperado: <b>${esc(d.local.nombre)} ${dec(e.esperado.local)}</b> · <b>${esc(d.visita.nombre)} ${dec(e.esperado.visita)}</b> · total <b>${dec(e.esperado.total)}</b>. Cruza lo que anota cada equipo con lo que recibe el rival en esa condición.</p>
  </section>`;
  for (const g of e.grupos) {
    html += `<section class="seccion"><h3>${esc(g.titulo)}</h3>${g.mercados.map((m) => mercado(pid, m)).join("")}</section>`;
  }
  return html;
}

function nbaBajas(d) {
  let html = "";
  for (const lado of ["visita", "local"]) {
    const eq = d[lado];
    const lista = d.bajas[lado] || [];
    html += `<section class="seccion"><h3><span>${escudo(eq.logo, "escudo")} ${esc(eq.nombre)}</span><small>${lista.length} en el parte</small></h3>
      <div class="lista">
        ${lista.length ? lista.map((b) => `<div><span>${esc(b.nombre)}${b.motivo ? ` <small>· ${esc(b.motivo)}</small>` : ""}${b.vuelve ? `<br><small>Regreso estimado: ${fechaCorta(b.vuelve + "T12:00:00Z")}</small>` : ""}${b.comentario ? `<br><small class="ingles">${esc(b.comentario)}</small>` : ""}</span><span class="tag ${ESTADO_BAJA[b.estado] || ""}">${esc(b.estado)}</span></div>`).join("") : "<div><small>Sin jugadores en el parte de lesiones</small></div>"}
      </div></section>`;
  }
  return html + '<p class="nota" style="padding:0 16px 16px">Fuente: parte de lesiones de ESPN. Los comentarios vienen en inglés.</p>';
}

function nbaHistorial(d) {
  const h = d.historial;
  let html = `<section class="seccion"><h3>Últimos enfrentamientos</h3><div class="lista">
    ${h.h2h.length ? h.h2h.map((m) => `<div><span>${esc(m.local)} <b>${esc(m.resultado)}</b> ${esc(m.visita)}<br><small>${fechaCorta(m.fecha)}</small></span></div>`).join("") : '<div><span class="tag amarillo">Faltan datos de enfrentamientos</span></div>'}
  </div></section>`;
  for (const [lado, clave] of [["visita", "forma_visita"], ["local", "forma_local"]]) {
    const f = h[clave];
    const eq = d[lado];
    html += `<section class="seccion"><h3><span>${escudo(eq.logo, "escudo")} ${esc(eq.nombre)}</span>
      <span class="forma">${f.map((x) => `<span class="res ${x.res}">${x.res}</span>`).join("")}</span></h3>
      <div class="lista">${f.length ? f.map((x) => `<div><span style="display:flex;gap:10px;align-items:center"><span class="res ${x.res}">${x.res}</span><span>${x.condicion === "L" ? "vs" : "en"} ${esc(x.rival)} <small>${x.pf}-${x.pc} · ${fechaCorta(x.fecha)}</small></span></span></div>`).join("") : '<div><span class="tag amarillo">Faltan datos</span></div>'}</div>
    </section>`;
  }
  return html;
}

async function nbaPartido(id, tab) {
  const pid = `nba-${id}`;
  app.dataset.pid = pid;
  let d = nba.partidos[id];
  if (!d) {
    app.innerHTML = '<p class="cargando">Cargando partido…</p>';
    try { d = nba.partidos[id] = await cargar(`data/nba/partido/${id}.json`); }
    catch (e) { app.innerHTML = errorCarga("#/nba"); return; }
  }
  tab = TABS_NBA.some(([k]) => k === tab) ? tab : "jugadores";
  const cuerpo = tab === "equipos" ? nbaEquipos(d, pid) : tab === "bajas" ? nbaBajas(d) : tab === "historial" ? nbaHistorial(d) : nbaJugadores(d, pid);
  const nBajas = d.bajas.local.length + d.bajas.visita.length;
  app.innerHTML = nbaCabecera(d)
    + `<nav class="tabs">${TABS_NBA.map(([k, n]) => `<a class="tab ${k === tab ? "activo" : ""}" href="#/nba/p/${id}/${k}">${n}${k === "bajas" && nBajas ? ` (${nBajas})` : ""}</a>`).join("")}</nav>`
    + cuerpo;
  app.querySelectorAll("[data-lado]").forEach((b) => b.addEventListener("click", () => {
    nba.lado = b.dataset.lado;
    nbaPartido(id, "jugadores");
  }));
}

async function vistaNba(id, tab) {
  if (!nba.indice) {
    try { nba.indice = await cargar("data/nba/proximos.json"); }
    catch (e) { app.innerHTML = errorCarga(); return; }
  }
  if (id) await nbaPartido(id, tab);
  else { delete app.dataset.pid; nbaInicio(); }
}
