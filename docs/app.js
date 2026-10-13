"use strict";

const TZ = "America/Argentina/Buenos_Aires";
const app = document.getElementById("app");
const estado = { indice: null, partidos: {}, jugadorLado: "local" };

// ---------------------------------------------------------------- utilidades

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const dec = (n, d = 1) => (n == null ? "–" : Number(n).toLocaleString("es-AR", { minimumFractionDigits: d, maximumFractionDigits: d }));
const pct = (p) => `${Math.round(p * 100)}%`;
const hora = (iso) => new Date(iso).toLocaleTimeString("es-AR", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const diaClave = (iso) => new Date(iso).toLocaleDateString("en-CA", { timeZone: TZ });
const fechaCorta = (iso) => new Date(iso).toLocaleDateString("es-AR", { timeZone: TZ, day: "2-digit", month: "2-digit", year: "2-digit" });

function nombreDia(iso) {
  const clave = diaClave(iso);
  const hoy = diaClave(new Date().toISOString());
  const manana = diaClave(new Date(Date.now() + 864e5).toISOString());
  if (clave === hoy) return "Hoy";
  if (clave === manana) return "Mañana";
  return new Date(iso).toLocaleDateString("es-AR", { timeZone: TZ, weekday: "long", day: "numeric", month: "long" });
}

function hace(iso) {
  const min = Math.round((Date.now() - new Date(iso)) / 60000);
  if (min < 1) return "recién";
  if (min < 60) return `hace ${min} min`;
  const h = Math.round(min / 60);
  return h < 24 ? `hace ${h} h` : `el ${fechaCorta(iso)}`;
}

const escudo = (url, cls = "") => (url ? `<img class="${cls}" src="${esc(url)}" alt="" loading="lazy">` : "");

function guardarLocal(clave, valor) { try { localStorage.setItem(clave, JSON.stringify(valor)); } catch (e) { /* modo privado */ } }
function leerLocal(clave, defecto) { try { return JSON.parse(localStorage.getItem(clave)) ?? defecto; } catch (e) { return defecto; } }

async function cargar(url) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

// ---------------------------------------------------------------- cuotas (se guardan en este celular)

const claveCuotas = (pid) => `dlt:cuotas:${pid}`;

function parseCuota(txt) {
  const n = parseFloat(String(txt).replace(",", "."));
  return n > 1 ? n : null;
}

function evaluar(prob, c365, cBet) {
  const a = parseCuota(c365), b = parseCuota(cBet);
  if (!a && !b) return { html: "", mejor: null };
  let mejor = null, texto = "";
  if (a && b) {
    if (a > b) { mejor = "b365"; texto = "bet365 paga más"; }
    else if (b > a) { mejor = "betano"; texto = "Betano paga más"; }
    else texto = "Pagan igual";
  }
  const cuota = Math.max(a || 0, b || 0);
  const valor = prob * cuota;
  const veredicto = valor > 1
    ? `<span class="si">Valor ${dec(valor, 2)} · tiene valor</span>`
    : `<span class="no">Valor ${dec(valor, 2)} · no conviene</span>`;
  return { html: `${texto ? `<span>${texto}</span>` : ""}${veredicto}`, mejor };
}

function mercado(pid, m, clave) {
  const k = clave || m.nombre;
  const guardadas = leerLocal(claveCuotas(pid), {})[k] || {};
  const ev = evaluar(m.prob, guardadas.b365, guardadas.betano);
  const justa = m.prob > 0 ? dec(1 / m.prob, 2) : "–";
  const color = m.prob >= 0.65 ? "var(--verde)" : m.prob <= 0.35 ? "var(--rojo)" : "var(--acento)";
  return `
  <div class="mercado" data-k="${esc(k)}" data-p="${m.prob}">
    <div class="m-fila"><span class="m-nombre">${esc(m.nombre)}</span><span class="m-prob">${pct(m.prob)}</span></div>
    <div class="barra"><i style="width:${Math.round(m.prob * 100)}%;background:${color}"></i></div>
    <div class="m-justa">Cuota justa DLT: ${justa}</div>
    <div class="cuotas">
      <div class="cuota ${ev.mejor === "b365" ? "mejor" : ""}"><label>bet365</label><input inputmode="decimal" data-casa="b365" placeholder="cuota" value="${esc(guardadas.b365 || "")}"></div>
      <div class="cuota ${ev.mejor === "betano" ? "mejor" : ""}"><label>Betano</label><input inputmode="decimal" data-casa="betano" placeholder="cuota" value="${esc(guardadas.betano || "")}"></div>
    </div>
    <div class="valor">${ev.html}</div>
  </div>`;
}

app.addEventListener("input", (e) => {
  const input = e.target.closest(".cuota input");
  if (!input) return;
  const fila = input.closest(".mercado");
  const pid = app.dataset.pid;
  const todas = leerLocal(claveCuotas(pid), {});
  const k = fila.dataset.k;
  todas[k] = { ...(todas[k] || {}), [input.dataset.casa]: input.value.trim() };
  guardarLocal(claveCuotas(pid), todas);
  const ev = evaluar(Number(fila.dataset.p), todas[k].b365, todas[k].betano);
  fila.querySelector(".valor").innerHTML = ev.html;
  fila.querySelectorAll(".cuota").forEach((c) => c.classList.toggle("mejor", c.querySelector("input").dataset.casa === ev.mejor));
});

// ---------------------------------------------------------------- pantalla principal

function vistaInicio() {
  const idx = estado.indice;
  const filtro = leerLocal("dlt:filtro", "todas");
  const comps = idx.competiciones;
  const nombreComp = Object.fromEntries(comps.map((c) => [c.id, c.nombre]));
  const lista = idx.partidos.filter((p) => filtro === "todas" || p.competicion === filtro);

  let html = `<nav class="chips">
    <button class="chip ${filtro === "todas" ? "activo" : ""}" data-filtro="todas">Todas</button>
    ${comps.map((c) => `<button class="chip ${filtro === c.id ? "activo" : ""}" data-filtro="${c.id}">${esc(c.nombre)}</button>`).join("")}
  </nav>`;

  if (!lista.length) {
    html += `<p class="vacio">No hay partidos hoy ni en los próximos dos días${filtro !== "todas" ? " para esta competición" : ""}.</p>`;
  }
  let diaActual = null;
  for (const p of lista) {
    const d = nombreDia(p.fecha);
    if (d !== diaActual) { html += `<h2 class="dia">${esc(d)}</h2>`; diaActual = d; }
    const enJuego = p.estado === "in";
    html += `
    <a class="partido" href="#/p/${p.id}">
      <div class="p-top"><span class="p-comp">${esc(nombreComp[p.competicion] || p.competicion)}</span>
        <span class="p-hora">${enJuego ? '<span class="tag rojo">EN JUEGO</span>' : hora(p.fecha)}</span></div>
      <div class="p-equipos">
        <div class="eq">${escudo(p.local.logo)}${esc(p.local.nombre)}</div>
        <div class="eq">${escudo(p.visita.logo)}${esc(p.visita.nombre)}</div>
      </div>
      <div class="p-info">
        <span>Árbitro: <b>${esc(p.arbitro || "sin designar")}</b></span>
        ${p.tarjetas_esperadas != null ? `<span><i class="tarjeta-ico"></i> <b>${dec(p.tarjetas_esperadas)}</b> tarjetas esperadas</span>` : ""}
      </div>
      <div class="p-info">
        ${p.bajas ? `<span class="tag rojo">${p.bajas} ${p.bajas === 1 ? "baja" : "bajas"}</span>` : ""}
        ${p.alineacion_confirmada ? '<span class="tag verde">Alineación confirmada</span>' : ""}
        ${p.pocos_datos ? '<span class="tag amarillo">Pocos datos</span>' : ""}
      </div>
    </a>`;
  }
  app.innerHTML = html;
  app.querySelectorAll("[data-filtro]").forEach((b) => b.addEventListener("click", () => {
    guardarLocal("dlt:filtro", b.dataset.filtro);
    vistaInicio();
  }));
}

// ---------------------------------------------------------------- detalle del partido

const TABS = [["tarjetas", "Tarjetas"], ["corners", "Córners"], ["faltas", "Faltas"], ["jugadores", "Jugadores"], ["bajas", "Bajas"], ["historial", "Historial"]];

function cabecera(d) {
  const a = d.arbitro;
  const arb = a
    ? `<b>${esc(a.nombre)}</b>${a.amarillas != null ? ` · ${dec(a.amarillas, 2)} amarillas por partido (liga ${dec(a.amarillas_liga, 2)})` : ""}`
    : "<b>Sin designar todavía</b>";
  return `
  <a class="volver" href="#/">‹ Partidos</a>
  <section class="cabecera">
    <div class="cab-comp">${esc(d.competicion_nombre)}</div>
    <div class="cab-equipos">
      <div class="cab-eq">${escudo(d.local.logo)}${esc(d.local.nombre)}</div>
      <div class="cab-hora"><b>${hora(d.fecha)}</b><span>${esc(nombreDia(d.fecha))}</span></div>
      <div class="cab-eq">${escudo(d.visita.logo)}${esc(d.visita.nombre)}</div>
    </div>
    <div class="cab-datos">
      <span>Estadio: <b>${esc(d.estadio || "–")}</b></span>
      <span>Árbitro: ${arb}</span>
      <span>Alineaciones: ${d.alineacion_confirmada ? '<b style="color:var(--verde)">confirmadas</b>' : "<b>sin confirmar</b> (se muestran las probables)"}</span>
    </div>
  </section>`;
}

function tabMetrica(d, metrica) {
  const t = d.analisis.tabs[metrica];
  if (!t) return `<p class="vacio">No hay datos suficientes para calcular este mercado.</p>`;
  const nombre = { tarjetas: "Tarjetas", corners: "Córners", faltas: "Faltas" }[metrica];
  let html = "";
  if (d.analisis.pocos_datos) {
    html += `<div class="aviso">Pocos datos: ${esc(d.local.nombre)} jugó ${d.analisis.partidos_local} de local y ${esc(d.visita.nombre)} ${d.analisis.partidos_visita} de visitante. Tomá los porcentajes con cuidado.</div>`;
  }
  if (metrica === "tarjetas") {
    const a = d.arbitro;
    html += `<section class="seccion"><h3>Árbitro <small>ajuste ×${dec(d.analisis.factor_arbitro, 2)}</small></h3>
      <p class="nota">${a && a.amarillas != null
        ? `${esc(a.nombre)} saca <b>${dec(a.amarillas, 2)}</b> amarillas por partido; el promedio de la liga es ${dec(a.amarillas_liga, 2)}. Por eso las tarjetas esperadas se multiplican por ${dec(d.analisis.factor_arbitro, 2)}.`
        : "Todavía no hay árbitro designado: se calcula sin ajuste. Cuando lo designen, se actualiza solo."}
      ${d.promedio_tarjetas_liga ? `<br>Promedio de tarjetas por partido en la liga: <b>${dec(d.promedio_tarjetas_liga, 2)}</b>.` : ""}</p></section>`;
  }
  const pr = t.promedios;
  html += `<section class="seccion"><h3>${nombre} esperadas <small>${dec(t.esperado.total, 2)} en total</small></h3>
    <table class="tabla">
      <tr><th>Promedio temporada</th><th class="n">Hace</th><th class="n">Recibe</th><th class="n">PJ</th></tr>
      <tr><td>${esc(d.local.nombre)} (local)</td><td class="n">${dec(pr.local.favor, 2)}</td><td class="n">${dec(pr.local.contra, 2)}</td><td class="n">${pr.local.n}</td></tr>
      <tr><td>${esc(d.visita.nombre)} (visitante)</td><td class="n">${dec(pr.visita.favor, 2)}</td><td class="n">${dec(pr.visita.contra, 2)}</td><td class="n">${pr.visita.n}</td></tr>
      <tr><td><b>Esperado este partido</b></td><td class="n">${dec(t.esperado.local, 2)}</td><td class="n">${dec(t.esperado.visita, 2)}</td><td></td></tr>
    </table>
    <p class="nota">"Esperado" cruza lo que hace cada equipo con lo que reciben sus rivales${metrica === "tarjetas" ? ", ajustado por el árbitro" : ""}. Columnas: local / visitante.</p>
  </section>`;
  for (const g of t.grupos) {
    html += `<section class="seccion"><h3>${esc(g.titulo)}</h3>${g.mercados.map((m) => mercado(d.id, m)).join("")}</section>`;
  }
  return html;
}

function tabJugadores(d) {
  const lado = estado.jugadorLado;
  const eq = d[lado];
  const lista = d.jugadores[lado] || [];
  let html = `<div class="selector">
    <button data-lado="local" class="${lado === "local" ? "activo" : ""}">${escudo(d.local.logo, "escudo")}${esc(d.local.nombre)}</button>
    <button data-lado="visita" class="${lado === "visita" ? "activo" : ""}">${escudo(d.visita.logo, "escudo")}${esc(d.visita.nombre)}</button>
  </div>`;
  html += `<p class="nota" style="padding:10px 16px">Promedios de los últimos 10 partidos de ${esc(eq.nombre)}. ${d.alineacion_confirmada ? "Arriba, los titulares confirmados." : "Arriba, el once probable (último once titular)."}</p>`;
  if (!lista.length) return html + `<p class="vacio">Sin datos de jugadores.</p>`;
  for (const j of lista) {
    const tags = [
      j.en_once ? `<span class="tag verde">${d.alineacion_confirmada ? "Titular" : "Probable titular"}</span>` : "",
      j.baja ? '<span class="tag rojo">Baja</span>' : "",
      j.pocos_datos ? '<span class="tag amarillo">Pocos datos</span>' : "",
    ].join("");
    const s = j.prom;
    const stats = j.pos === "G"
      ? `<span>Atajadas <b>${dec(s.atajadas, 2)}</b></span>`
      : `<span>Remates <b>${dec(s.remates, 2)}</b></span><span>Al arco <b>${dec(s.remates_arco, 2)}</b></span><span>Faltas <b>${dec(s.faltas, 2)}</b></span><span>Amarillas <b>${dec(s.amarillas, 2)}</b></span>`;
    html += `<section class="seccion jugador">
      <h3><span>${esc(j.nombre)} <small>${esc(j.pos === "G" ? "Arquero" : j.pos || "")} · ${j.n} PJ</small></span><span>${tags}</span></h3>
      <div class="jug-stats">${stats}</div>
      <div class="mini">${j.mercados.map((m) => `<div><span>${esc(m.nombre)}</span><span class="barra"><i style="width:${Math.round(m.prob * 100)}%"></i></span><b>${pct(m.prob)}</b></div>`).join("")}</div>
      <details><summary>Comparar cuotas</summary>
        ${j.mercados.map((m) => mercado(d.id, { nombre: m.nombre, prob: m.prob }, `j${j.id}:${m.nombre}`)).join("")}
      </details>
    </section>`;
  }
  return html;
}

function tabBajas(d) {
  let html = "";
  for (const lado of ["local", "visita"]) {
    const b = d.bajas[lado];
    const eq = d[lado];
    html += `<section class="seccion"><h3><span>${escudo(eq.logo, "escudo")} ${esc(eq.nombre)}</span><small>${b.bajas.length} bajas</small></h3>
      <div class="lista">
        ${b.bajas.length ? b.bajas.map((x) => `<div><span>${esc(x.nombre)}${x.vuelve ? `<br><small>Vuelve: ${esc(x.vuelve)}</small>` : ""}</span><span class="tag rojo">${esc(x.tipo)}</span></div>`).join("") : '<div><small>Sin bajas informadas</small></div>'}
      </div>
      <h3 style="background:none;border-top:1px solid var(--borde)">En riesgo por amarillas</h3>
      <div class="lista">
        ${b.riesgo.length ? b.riesgo.map((x) => `<div><span>${esc(x.nombre)}</span><span class="tag amarillo">${x.amarillas} amarillas</span></div>`).join("") : "<div><small>Nadie al borde de la suspensión</small></div>"}
      </div>
    </section>`;
  }
  html += `<p class="nota" style="padding:0 16px 16px">Lesionados: FotMob. Suspensiones y riesgo: calculados por DLT con las amarillas del torneo (estimado).</p>`;
  return html;
}

function filaForma(f) {
  const res = f.res ? `<span class="res ${f.res}">${f.res}</span>` : '<span class="res x">?</span>';
  const extra = f.faltan_datos ? '<span class="tag amarillo">faltan datos</span>'
    : `<small><i class="tarjeta-ico"></i> ${dec(f.tarjetas, 0)} · córners ${dec(f.corners, 0)}</small>`;
  return `<div><span style="display:flex;gap:10px;align-items:center">${res}<span>${f.condicion === "L" ? "vs" : "en"} ${esc(f.rival)} <small>${f.gf ?? "–"}-${f.gc ?? "–"} · ${fechaCorta(f.fecha)}</small></span></span>${extra}</div>`;
}

function tabHistorial(d) {
  const h = d.historial;
  let html = "";
  html += `<section class="seccion"><h3>Últimos enfrentamientos</h3><div class="lista">
    ${h.h2h.length ? h.h2h.map((m) => `<div><span>${esc(m.local)} <b>${esc(m.resultado)}</b> ${esc(m.visita)}<br><small>${esc(m.torneo || "")} · ${fechaCorta(m.fecha)}</small></span></div>`).join("") : '<div><span class="tag amarillo">Faltan datos de enfrentamientos</span></div>'}
  </div></section>`;
  if (h.h2h_temporada.length) {
    html += `<section class="seccion"><h3>Esta temporada entre ellos</h3><div class="lista">
      ${h.h2h_temporada.map((m) => `<div><span>${esc(m.local)} <b>${esc(m.resultado)}</b> ${esc(m.visita)}<br><small>${fechaCorta(m.fecha)}</small></span>${m.faltan_datos ? '<span class="tag amarillo">faltan datos</span>' : `<small><i class="tarjeta-ico"></i> ${dec(m.tarjetas, 0)} · córners ${dec(m.corners, 0)}</small>`}</div>`).join("")}
    </div></section>`;
  }
  for (const [lado, clave] of [["local", "forma_local"], ["visita", "forma_visita"]]) {
    const f = h[clave];
    const eq = d[lado];
    html += `<section class="seccion"><h3><span>${escudo(eq.logo, "escudo")} ${esc(eq.nombre)}</span>
      <span class="forma">${f.map((x) => `<span class="res ${x.res || "x"}">${x.res || "?"}</span>`).join("")}</span></h3>
      <div class="lista">${f.length ? f.map(filaForma).join("") : '<div><span class="tag amarillo">Faltan datos</span></div>'}</div>
    </section>`;
  }
  return html;
}

async function vistaPartido(id, tab) {
  app.dataset.pid = id;
  let d = estado.partidos[id];
  if (!d) {
    app.innerHTML = '<p class="cargando">Cargando partido…</p>';
    try { d = estado.partidos[id] = await cargar(`data/partido/${id}.json`); }
    catch (e) { app.innerHTML = '<a class="volver" href="#/">‹ Partidos</a><p class="vacio">Este partido ya no está disponible.</p>'; return; }
  }
  tab = TABS.some(([k]) => k === tab) ? tab : "tarjetas";
  const cuerpo = tab === "jugadores" ? tabJugadores(d) : tab === "bajas" ? tabBajas(d) : tab === "historial" ? tabHistorial(d) : tabMetrica(d, tab);
  const nBajas = d.bajas.local.bajas.length + d.bajas.visita.bajas.length;
  app.innerHTML = cabecera(d)
    + `<nav class="tabs">${TABS.map(([k, n]) => `<a class="tab ${k === tab ? "activo" : ""}" href="#/p/${id}/${k}">${n}${k === "bajas" && nBajas ? ` (${nBajas})` : ""}</a>`).join("")}</nav>`
    + cuerpo;
  app.querySelectorAll("[data-lado]").forEach((b) => b.addEventListener("click", () => {
    estado.jugadorLado = b.dataset.lado;
    vistaPartido(id, "jugadores");
  }));
}

// ---------------------------------------------------------------- arranque

async function router() {
  const [, ruta, id, tab] = location.hash.split("/");
  if (!estado.indice) {
    try { estado.indice = await cargar("data/proximos.json"); }
    catch (e) { app.innerHTML = '<p class="vacio">No se pudieron cargar los datos. Probá de nuevo en un rato.</p>'; return; }
    document.getElementById("actualizado").textContent = `Actualizado ${hace(estado.indice.actualizado)}`;
  }
  const scroll = ruta === "p" && tab;
  if (ruta === "p" && id) await vistaPartido(id, tab);
  else { delete app.dataset.pid; vistaInicio(); }
  if (!scroll) window.scrollTo(0, 0);
}

window.addEventListener("hashchange", router);
router();
