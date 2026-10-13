"""Formula 1: calendario, estadisticas de pilotos, historial del circuito, campeonatos y sanciones.
Fuentes: Jolpica-F1 (resultados, sin clave) y OpenF1 (horarios y sanciones de comisarios, sin clave).

Uso:
  python scripts/f1.py              actualizacion completa
  python scripts/f1.py --sanciones  solo revisa los mensajes de los comisarios (rapido, cada 15 min)
"""
import hashlib
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import fuentes
from actualizar import fecha_utc, guardar, leer
from config import CACHE, RAIZ

JOLPICA = "https://api.jolpi.ca/ergast/f1"
OPENF1 = "https://api.openf1.org/v1"
SALIDA = RAIZ / "docs" / "data" / "f1"
CARPETA = CACHE / "f1"
ANIOS_CIRCUITO = 5
ULTIMAS_CARRERAS = 8  # para las probabilidades pesan mas las carreras recientes

SESIONES = [("FirstPractice", "Práctica 1"), ("SecondPractice", "Práctica 2"), ("ThirdPractice", "Práctica 3"),
            ("SprintQualifying", "Clasificación sprint"), ("Sprint", "Sprint"), ("Qualifying", "Clasificación")]
ABANDONO = ("Retired", "Did not start", "Disqualified", "Withdrew", "Did not qualify", "Not classified")

estado_fuentes = {}


def pedir(url, fuente):
    try:
        data = fuentes.bajar(url, "espn")  # el contador de fuentes.py se usa solo para estadisticas
        estado_fuentes.setdefault(fuente, {"ok": True})
        time.sleep(0.3)  # Jolpica pide no mas de 4 consultas por segundo
        return data
    except Exception as err:
        estado_fuentes[fuente] = {"ok": False, "error": str(err)[:120]}
        raise


def jolpica(ruta):
    return pedir(f"{JOLPICA}/{ruta}", "Jolpica")


def jolpica_todo(ruta, clave):
    """Jolpica devuelve de a 100 resultados: junta todas las paginas."""
    carreras, offset = {}, 0
    while True:
        mr = jolpica(f"{ruta}?limit=100&offset={offset}")["MRData"]
        for r in mr["RaceTable"]["Races"]:
            carreras.setdefault(r["round"], {**r, clave: []})[clave] += r.get(clave, [])
        offset += 100
        if offset >= int(mr["total"]):
            return [carreras[k] for k in sorted(carreras, key=int)]


def fecha_sesion(s):
    return f"{s['date']}T{s.get('time', '00:00:00Z')}"


# ---------------------------------------------------------------- estadisticas

def nombre_piloto(d):
    return f"{d['givenName']} {d['familyName']}"


def pos(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def estadisticas_pilotos(carreras, clasif, standings):
    pilotos = {}
    for st in standings:
        d = st["Driver"]
        pilotos[d["driverId"]] = {
            "id": d["driverId"], "nombre": nombre_piloto(d), "codigo": d.get("code"), "numero": d.get("permanentNumber"),
            "equipo": st["Constructors"][-1]["name"] if st.get("Constructors") else None,
            "puntos": float(st["points"]), "posicion": pos(st["position"]), "victorias": int(st["wins"]),
            "carreras": 0, "suma_carrera": 0, "terminadas": 0, "podios": 0, "abandonos": 0, "vueltas_rapidas": 0,
            "suma_quali": 0, "qualis": 0, "duelo_quali": [0, 0], "duelo_carrera": [0, 0], "companero": None,
            "historial": [],
        }
    for r in carreras:
        por_equipo = {}
        for x in r["Results"]:
            p = pilotos.get(x["Driver"]["driverId"])
            if not p:
                continue
            p["carreras"] += 1
            fin = pos(x["position"])
            abandono = any(x["status"].startswith(a) for a in ABANDONO)
            if abandono:
                p["abandonos"] += 1
            else:
                p["terminadas"] += 1
                p["suma_carrera"] += fin
            if fin and fin <= 3 and not abandono:
                p["podios"] += 1
            if (x.get("FastestLap") or {}).get("rank") == "1":
                p["vueltas_rapidas"] += 1
            p["historial"].append({"ronda": int(r["round"]), "gp": r["raceName"], "pos": None if abandono else fin,
                                   "grid": pos(x.get("grid")), "estado": x["status"], "puntos": float(x["points"])})
            por_equipo.setdefault(x["Constructor"]["constructorId"], []).append((p, None if abandono else fin))
        for dupla in por_equipo.values():
            if len(dupla) == 2:
                (a, fa), (b, fb) = dupla
                a["companero"], b["companero"] = b["nombre"], a["nombre"]
                if fa or fb:
                    gana_a = fa is not None and (fb is None or fa < fb)
                    a["duelo_carrera"][0 if gana_a else 1] += 1
                    b["duelo_carrera"][1 if gana_a else 0] += 1
    for r in clasif:
        por_equipo = {}
        for x in r["QualifyingResults"]:
            p = pilotos.get(x["Driver"]["driverId"])
            q = pos(x["position"])
            if not p or not q:
                continue
            p["qualis"] += 1
            p["suma_quali"] += q
            por_equipo.setdefault(x["Constructor"]["constructorId"], []).append((p, q))
        for dupla in por_equipo.values():
            if len(dupla) == 2:
                (a, qa), (b, qb) = dupla
                a["duelo_quali"][0 if qa < qb else 1] += 1
                b["duelo_quali"][1 if qa < qb else 0] += 1
    salida = []
    for p in pilotos.values():
        salida.append({**{k: p[k] for k in ("id", "nombre", "codigo", "numero", "equipo", "puntos", "posicion",
                                              "victorias", "carreras", "podios", "abandonos", "vueltas_rapidas",
                                              "duelo_quali", "duelo_carrera", "companero")},
                       "prom_carrera": round(p["suma_carrera"] / p["terminadas"], 1) if p["terminadas"] else None,
                       "prom_quali": round(p["suma_quali"] / p["qualis"], 1) if p["qualis"] else None,
                       "ultimas": p["historial"][-5:]})
    salida.sort(key=lambda p: p["posicion"] or 99)
    return salida, pilotos


def probabilidades(pilotos_raw):
    """Estimacion simple: frecuencia de ganar / podio / puntos / abandonar en las ultimas carreras,
    con mas peso a las recientes y suavizada para que nadie quede en 0% o 100%."""
    filas = []
    for p in pilotos_raw.values():
        h = p["historial"][-ULTIMAS_CARRERAS:]
        if not h:
            continue
        pesos = [0.85 ** (len(h) - 1 - i) for i in range(len(h))]
        total = sum(pesos)
        frec = lambda cond: sum(w for w, x in zip(pesos, h) if cond(x)) / total
        filas.append({"id": p["id"], "nombre": p["nombre"],
                      "gana": frec(lambda x: x["pos"] == 1), "podio": frec(lambda x: x["pos"] and x["pos"] <= 3),
                      "puntos": frec(lambda x: x["pos"] and x["pos"] <= 10), "abandona": frec(lambda x: x["pos"] is None),
                      "duelo": (p["duelo_carrera"][0] + 1) / (sum(p["duelo_carrera"]) + 2), "companero": p["companero"]})
    n = len(filas) or 1
    # punto de partida para suavizar: ganar se apoya en los podios, el podio en los puntos, los puntos parejo
    def reparto(clave):
        total = sum(f[clave] for f in filas)
        return [f[clave] / total if total else 1 / n for f in filas]
    base = {"gana": reparto("podio"), "podio": reparto("puntos"), "puntos": [1 / n] * n}
    for clave, cupos in (("puntos", 10), ("podio", 3), ("gana", 1)):
        suavizado = [(f[clave] * ULTIMAS_CARRERAS + 2 * cupos * b) / (ULTIMAS_CARRERAS + 2)
                     for f, b in zip(filas, base[clave])]
        suma = sum(suavizado) or 1
        for f, v in zip(filas, suavizado):
            f[clave] = round(min(0.97, v * cupos / suma), 3)  # que entre todos sumen 1 ganador, 3 podios, 10 en puntos
    for f in filas:
        f["podio"] = max(f["podio"], f["gana"])  # coherencia: puntos >= podio >= ganar
        f["puntos"] = max(f["puntos"], f["podio"])
        f["abandona"] = round((f["abandona"] * ULTIMAS_CARRERAS + 0.1) / (ULTIMAS_CARRERAS + 1), 3)
        f["duelo"] = round(f["duelo"], 3)
    filas.sort(key=lambda f: -f["gana"])
    return filas


def historial_circuito(circuito_id, anio_actual):
    anios = {}
    for anio in range(anio_actual - ANIOS_CIRCUITO, anio_actual):
        archivo = CARPETA / "circuitos" / f"{circuito_id}_{anio}.json"
        datos = leer(archivo)
        if datos is None:
            races = jolpica(f"{anio}/circuits/{circuito_id}/results.json?limit=40")["MRData"]["RaceTable"]["Races"]
            datos = [{"id": x["Driver"]["driverId"], "nombre": nombre_piloto(x["Driver"]), "equipo": x["Constructor"]["name"],
                      "pos": None if any(x["status"].startswith(a) for a in ABANDONO) else pos(x["position"]),
                      "grid": pos(x.get("grid")), "estado": x["status"]} for r in races for x in r["Results"]]
            guardar(archivo, datos)
        if datos:
            anios[anio] = datos
    return anios


# ---------------------------------------------------------------- sanciones (OpenF1)

PATRON_SANCION = re.compile(r"PENALTY|REPRIMAND|DISQUALIFIED|BLACK AND WHITE|GRID|INVESTIGATION|NO FURTHER", re.I)


def tipo_sancion(msg):
    m = msg.upper()
    if "GRID" in m and "PENALTY" in m:
        return "grilla"
    if "DISQUALIFIED" in m:
        return "descalificado"
    if "PENALTY" in m and "NO PENALTY" not in m and "NO FURTHER" not in m:
        return "penalización"
    if "REPRIMAND" in m:
        return "reprimenda"
    if "UNDER INVESTIGATION" in m or "NOTED" in m:
        return "investigación"
    return "sin sanción"


def sanciones_de(sesiones, codigos):
    lista = []
    for s in sesiones:
        try:
            mensajes = pedir(f"{OPENF1}/race_control?session_key={s['session_key']}", "OpenF1")
        except Exception as err:
            print(f"  ! OpenF1 {s['session_name']}: {err}")
            continue
        for m in mensajes:
            texto = m.get("message") or ""
            if not texto.startswith("FIA STEWARDS") or not PATRON_SANCION.search(texto):
                continue
            auto = re.search(r"CARS? (\d+) \((\w{3})\)", texto)
            lista.append({
                "id": hashlib.sha1(f"{s['session_key']}|{m.get('date')}|{texto}".encode()).hexdigest()[:12],
                "sesion": s["session_name"], "gp": s.get("location"), "fecha": m.get("date"),
                "tipo": tipo_sancion(texto), "texto": texto.replace("FIA STEWARDS: ", ""),
                "piloto": codigos.get(auto.group(2)) if auto else None, "codigo": auto.group(2) if auto else None,
            })
    lista.sort(key=lambda x: x["fecha"] or "", reverse=True)
    return lista


def sesiones_openf1(anio):
    return pedir(f"{OPENF1}/sessions?year={anio}", "OpenF1")


def sesiones_relevantes(todas, proximo_inicio, ahora):
    """Sesiones del fin de semana actual o proximo que ya terminaron, mas la ultima carrera
    (ahi suelen anunciar penalizaciones de grilla para la carrera siguiente)."""
    terminadas = [s for s in todas if s.get("date_end") and fecha_utc(s["date_end"]) < ahora]
    if not terminadas:
        return []
    ultima_carrera = [s for s in terminadas if s["session_name"] == "Race"][-1:]
    del_finde = [s for s in terminadas if proximo_inicio and fecha_utc(s["date_start"]) >= proximo_inicio - timedelta(days=1)]
    vistas = {s["session_key"]: s for s in ultima_carrera + del_finde}
    return sorted(vistas.values(), key=lambda s: s["date_start"])


# ---------------------------------------------------------------- armado

def completo(ahora):
    anio = ahora.year
    calendario = jolpica(f"{anio}.json")["MRData"]["RaceTable"]["Races"]
    futuras = [r for r in calendario if fecha_utc(fecha_sesion(r)) > ahora - timedelta(hours=3)]
    if not futuras:  # temporada terminada: se muestra la del año siguiente cuando exista
        anio += 1
        calendario = jolpica(f"{anio}.json")["MRData"]["RaceTable"]["Races"] or calendario
        futuras = calendario
    prox = futuras[0]
    sesiones = [{"nombre": nombre, "fecha": fecha_sesion(prox[k])} for k, nombre in SESIONES if k in prox]
    sesiones.append({"nombre": "Carrera", "fecha": fecha_sesion(prox)})
    sesiones.sort(key=lambda s: s["fecha"])

    carreras = jolpica_todo(f"{anio}/results.json", "Results")
    clasif = jolpica_todo(f"{anio}/qualifying.json", "QualifyingResults")
    standings = jolpica(f"{anio}/driverStandings.json")["MRData"]["StandingsTable"]["StandingsLists"]
    constructores = jolpica(f"{anio}/constructorStandings.json")["MRData"]["StandingsTable"]["StandingsLists"]
    pilotos, crudos = estadisticas_pilotos(carreras, clasif, standings[0]["DriverStandings"] if standings else [])
    probs = probabilidades(crudos)
    circuito = historial_circuito(prox["Circuit"]["circuitId"], anio)

    codigos = {p["codigo"]: p["nombre"] for p in pilotos if p["codigo"]}
    try:
        todas = sesiones_openf1(anio)
        sanciones = sanciones_de(sesiones_relevantes(todas, fecha_utc(sesiones[0]["fecha"]), ahora), codigos)
    except Exception as err:
        print(f"  ! OpenF1: {err}")
        sanciones = (leer(SALIDA / "gp.json", {}) or {}).get("sanciones", [])

    nombres_hist = {}
    for lista in circuito.values():
        for x in lista:
            nombres_hist[x["id"]] = x["nombre"]
    actuales = {p["id"] for p in pilotos}
    return {
        "temporada": anio, "ronda": int(prox["round"]), "total_rondas": len(calendario),
        "gp": {"nombre": prox["raceName"], "circuito": prox["Circuit"]["circuitName"],
               "localidad": prox["Circuit"]["Location"]["locality"], "pais": prox["Circuit"]["Location"]["country"],
               "sprint": "Sprint" in prox, "sesiones": sesiones},
        "carreras_disputadas": len(carreras),
        "pilotos": pilotos,
        "probabilidades": probs,
        "circuito": {
            "anios": sorted(circuito),
            "pilotos": sorted(
                [{"id": pid, "nombre": nombres_hist[pid], "actual": pid in actuales,
                  "resultados": {str(a): next(({"pos": x["pos"], "grid": x["grid"], "estado": x["estado"], "equipo": x["equipo"]}
                                              for x in circuito[a] if x["id"] == pid), None) for a in sorted(circuito)}}
                 for pid in nombres_hist],
                key=lambda p: (not p["actual"], min([r["pos"] or 30 for r in p["resultados"].values() if r] or [30]))),
        },
        "campeonato": {
            "ronda": int(standings[0]["round"]) if standings else 0,
            "pilotos": [{"pos": p["posicion"], "nombre": p["nombre"], "equipo": p["equipo"], "puntos": p["puntos"],
                         "victorias": p["victorias"]} for p in pilotos],
            "constructores": [{"pos": pos(c["position"]), "nombre": c["Constructor"]["name"], "puntos": float(c["points"]),
                               "victorias": int(c["wins"])}
                              for c in (constructores[0]["ConstructorStandings"] if constructores else [])],
        },
        "sanciones": sanciones,
    }


def solo_sanciones(ahora):
    """Modo rapido: solo durante el fin de semana de carrera (y hasta 2 dias despues)."""
    datos = leer(SALIDA / "gp.json")
    if not datos or not datos.get("gp"):
        return
    inicio = fecha_utc(datos["gp"]["sesiones"][0]["fecha"])
    fin = fecha_utc(datos["gp"]["sesiones"][-1]["fecha"])
    if not (inicio - timedelta(hours=2) <= ahora <= fin + timedelta(days=2)):
        print("F1: no es fin de semana de carrera, no se revisan sanciones")
        return
    codigos = {p["codigo"]: p["nombre"] for p in datos["pilotos"] if p["codigo"]}
    todas = sesiones_openf1(datos["temporada"])
    datos["sanciones"] = sanciones_de(sesiones_relevantes(todas, inicio, ahora), codigos)
    datos["fuentes"] = {**datos.get("fuentes", {}), **estado_fuentes}
    guardar(SALIDA / "gp.json", datos)
    print(f"F1: {len(datos['sanciones'])} mensajes de comisarios")


def main():
    ahora = datetime.now(timezone.utc)
    if "--sanciones" in sys.argv:
        try:
            solo_sanciones(ahora)
        except Exception as err:
            print(f"!! F1 sanciones: {err}")
        return
    previo = leer(SALIDA / "gp.json", {}) or {}
    try:
        datos = completo(ahora)
        datos["actualizado"] = ahora.isoformat(timespec="seconds")
    except Exception as err:
        print(f"!! F1: {err}")
        datos = previo
    datos["fuentes"] = {**previo.get("fuentes", {}), **estado_fuentes}
    guardar(SALIDA / "gp.json", datos)
    if datos.get("gp"):
        print(f"Listo F1: {datos['gp']['nombre']} (ronda {datos['ronda']}), {len(datos['pilotos'])} pilotos, "
              f"{len(datos['sanciones'])} mensajes de comisarios")


if __name__ == "__main__":
    main()
