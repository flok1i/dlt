"use strict";
// Navegacion entre Futbol, NBA y F1. Rutas: #/ (futbol), #/p/ID/tab, #/nba, #/nba/p/ID/tab, #/f1

function marcarDeporte(deporte) {
  document.querySelectorAll(".deportes a").forEach((a) => a.classList.toggle("activo", a.dataset.deporte === deporte));
}

async function vistaFutbol(ruta, id, tab) {
  if (!estado.indice) {
    try { estado.indice = await cargar("data/proximos.json"); }
    catch (e) { app.innerHTML = errorCarga(); return; }
  }
  if (ruta === "p" && id) await vistaPartido(id, tab);
  else { delete app.dataset.pid; vistaInicio(); }
}

function vistaF1() {
  delete app.dataset.pid;
  app.innerHTML = '<p class="vacio">La sección de Fórmula 1 está en preparación.</p>';
}

async function router() {
  const partes = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const deporte = ["nba", "f1"].includes(partes[0]) ? partes.shift() : "futbol";
  const [ruta, id, tab] = partes;
  marcarDeporte(deporte);
  guardarLocal("dlt:deporte", deporte);
  if (deporte === "nba") await vistaNba(ruta === "p" ? id : null, tab);
  else if (deporte === "f1") vistaF1();
  else await vistaFutbol(ruta, id, tab);
  if (!(ruta === "p" && tab)) window.scrollTo(0, 0);
}

window.addEventListener("hashchange", router);
// si no hay ruta, abre el ultimo deporte que se miro en este celular
const ultimo = leerLocal("dlt:deporte", "futbol");
if ((!location.hash || location.hash === "#/") && ultimo !== "futbol") location.hash = `#/${ultimo}`;  // dispara router
else router();
