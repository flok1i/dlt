"""Baja los datos del dia, calcula probabilidades y genera los JSON de la pagina.

Uso: python scripts/actualizar.py
"""
import json
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

import calculos
import fuentes
from config import CACHE, COMPETICIONES, DIAS_ADELANTE, HORA_ARG, SALIDA


def leer(path, defecto=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return defecto


def guardar(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def fecha_utc(txt):
    return datetime.fromisoformat(txt.replace("Z", "+00:00")).astimezone(timezone.utc)


def normalizar(nombre):
    nombre = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    nombre = re.sub(r"\(.*?\)", "", nombre)
    nombre = re.sub(r"\b(club|atletico|ca|cd|fc|de|la|el)\b", " ", nombre)
    return re.sub(r"[^a-z0-9]+", " ", nombre).strip()


def parecido(a, b):
    a, b = normalizar(a), normalizar(b)
    if a and b and (a in b or b in a):
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------- ESPN

def equipo_espn(comp):
    t = comp["team"]
    return {"id": t["id"], "nombre": (t.get("shortDisplayName") or t["displayName"]).strip(),
            "nombre_largo": t["displayName"].strip(), "logo": t.get("logo")}


def evento_compacto(e):
    c = e["competitions"][0]
    eq = {x["homeAway"]: x for x in c["competitors"]}
    return {
        "id": e["id"], "fecha": e["date"], "estado": e["status"]["type"]["state"],
        "torneo": (e.get("season") or {}).get("slug"),
        "local": equipo_espn(eq["home"]), "visita": equipo_espn(eq["away"]),
        "goles": [eq["home"].get("score"), eq["away"].get("score")],
        "estadio": (c.get("venue") or {}).get("fullName"),
    }


def calendario(comp, hoy):
    """Lista de partidos de la temporada hasta hoy + DIAS_ADELANTE (dias pasados cacheados)."""
    actual = fuentes.espn_dia(comp["espn"], hoy)
    fechas = sorted({fecha_utc(f).date() for f in actual["leagues"][0].get("calendar", [])
                     if isinstance(f, str)})
    limite = hoy + timedelta(days=DIAS_ADELANTE)
    carpeta = CACHE / comp["id"] / "dias"
    eventos = {}

    def dia(f):
        archivo = carpeta / f"{f:%Y%m%d}.json"
        guardado = leer(archivo)
        if guardado is not None and f < hoy - timedelta(days=1):
            return guardado
        data = actual if f == hoy else fuentes.espn_dia(comp["espn"], f)
        lista = [evento_compacto(e) for e in data.get("events", [])]
        guardar(archivo, lista)
        return lista

    pedir = [f for f in fechas if f <= limite]
    # el dia de hoy y los proximos siempre se piden aunque no esten en el calendario
    pedir += [hoy + timedelta(days=i) for i in range(DIAS_ADELANTE + 1) if hoy + timedelta(days=i) not in pedir]
    with ThreadPoolExecutor(4) as pool:
        for lista in pool.map(dia, pedir):
            for ev in lista:
                eventos[ev["id"]] = ev
    return sorted(eventos.values(), key=lambda e: e["fecha"])


def num(stats, nombre):
    try:
        return float(stats.get(nombre, 0) or 0)
    except ValueError:
        return 0.0


def partido_compacto(ev, s):
    """Del resumen de ESPN se queda solo con lo que usamos."""
    stats = {}
    for t in s.get("boxscore", {}).get("teams", []):
        st = {x["name"]: x.get("displayValue") for x in t.get("statistics", [])}
        if "foulsCommitted" not in st:
            continue
        lado = "h" if t.get("homeAway") == "home" else "a"
        stats[lado] = {
            "tarjetas": num(st, "yellowCards") + num(st, "redCards"),
            "amarillas": num(st, "yellowCards"), "rojas": num(st, "redCards"),
            "corners": num(st, "wonCorners"), "faltas": num(st, "foulsCommitted"),
            "remates": num(st, "totalShots"), "remates_arco": num(st, "shotsOnTarget"),
            "atajadas": num(st, "saves"),
        }
    jugadores = []
    for r in s.get("rosters", []):
        lado = "h" if r.get("homeAway") == "home" else "a"
        for j in r.get("roster", []):
            st = {x["name"]: x.get("displayValue") for x in j.get("stats", [])}
            jugadores.append({
                "id": j["athlete"]["id"], "nombre": j["athlete"].get("displayName"), "lado": lado,
                "pos": (j.get("position") or {}).get("abbreviation"),
                "titular": bool(j.get("starter")),
                "jugo": bool(j.get("starter") or j.get("subbedIn") or num(st, "appearances") > 0),
                "remates": num(st, "totalShots"), "remates_arco": num(st, "shotsOnTarget"),
                "faltas": num(st, "foulsCommitted"), "amarillas": num(st, "yellowCards"),
                "rojas": num(st, "redCards"), "atajadas": num(st, "saves"),
            })
    return {**ev, "stats": stats if len(stats) == 2 else None, "jugadores": jugadores or None}


def jugados_con_detalle(comp, eventos):
    carpeta = CACHE / comp["id"] / "partidos"
    jugados = [e for e in eventos if e["estado"] == "post"]
    faltan = [e for e in jugados if not (carpeta / f"{e['id']}.json").exists()]
    if faltan:
        print(f"  bajando {len(faltan)} partidos jugados nuevos...")

    def bajar(e):
        try:
            guardar(carpeta / f"{e['id']}.json", partido_compacto(e, fuentes.espn_partido(comp["espn"], e["id"])))
        except Exception as err:  # un partido que falla no frena el resto; se reintenta en la proxima corrida
            print(f"  ! no se pudo bajar {e['id']}: {err}")

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(bajar, faltan))
    return [p for p in (leer(carpeta / f"{e['id']}.json") for e in jugados) if p]


# ---------------------------------------------------------------- FotMob

def fotmob_partidos(comp, desde, hasta):
    vistos = {}
    f = desde - timedelta(days=1)
    while f <= hasta + timedelta(days=1):
        try:
            data = fuentes.fotmob_dia(f)
        except Exception as err:
            print(f"  ! FotMob {f}: {err}")
            data = {}
        for liga in data.get("leagues", []):
            if liga.get("primaryId") == comp["fotmob"]:
                for m in liga.get("matches", []):
                    vistos[m["id"]] = m
        f += timedelta(days=1)
    return list(vistos.values())


def emparejar(ev, candidatos):
    inicio = fecha_utc(ev["fecha"])
    mejor, puntaje = None, 0
    for m in candidatos:
        if abs((fecha_utc(m["status"]["utcTime"]) - inicio).total_seconds()) > 3 * 3600:
            continue
        p = parecido(ev["local"]["nombre_largo"], m["home"]["name"]) + parecido(ev["visita"]["nombre_largo"], m["away"]["name"])
        if p > puntaje:
            mejor, puntaje = m, p
    return mejor if puntaje >= 1.2 else None


def detalle_fotmob(match_id):
    md = fuentes.fotmob_partido(match_id)
    c = md.get("content", {})
    info = c.get("matchFacts", {}).get("infoBox", {}) or {}
    arbitro = None
    ref = info.get("Referee")
    if ref and ref.get("text"):
        arbitro = {"nombre": ref["text"]}
        for st in ref.get("stats", []) or []:
            if st.get("type") == "yellowCards":
                arbitro["amarillas"] = st.get("value")
                arbitro["amarillas_liga"] = st.get("average")
            elif st.get("type") == "matches":
                arbitro["partidos"] = st.get("value")
            elif st.get("type") == "fouls":
                arbitro["faltas"] = st.get("value")
    lu = c.get("lineup") or {}
    tipo = lu.get("lineupType")
    def lado(k):
        t = lu.get(k) or {}
        return {
            "bajas": [{"nombre": p.get("name"), "tipo": (p.get("unavailability") or {}).get("type"),
                       "vuelve": (p.get("unavailability") or {}).get("expectedReturn")}
                      for p in t.get("unavailable", []) or []],
            "titulares": [p.get("name") for p in t.get("starters", []) or []],
            "formacion": t.get("formation"),
        }
    h2h = []
    for m in (c.get("h2h") or {}).get("matches", [])[:8]:
        st = m.get("status", {})
        if not st.get("finished"):
            continue
        h2h.append({"fecha": st.get("utcTime"), "local": m["home"]["name"], "visita": m["away"]["name"],
                    "resultado": st.get("scoreStr"), "torneo": (m.get("league") or {}).get("name")})
    estadio = (info.get("Stadium") or {}).get("name")
    return {"arbitro": arbitro, "local": lado("homeTeam"), "visita": lado("awayTeam"),
            "alineacion_confirmada": tipo == "standard", "tipo_alineacion": tipo,
            "h2h": h2h, "estadio": estadio}


# ---------------------------------------------------------------- armado

TIPOS_BAJA = {"injury": "Lesionado", "red_card": "Suspendido (roja)", "yellow_card": "Suspendido (amarillas)",
              "suspension": "Suspendido", "international_duty": "Selección", "doubtful": "Duda"}


def riesgo_amarillas(partidos, equipo_id, torneo, limite):
    """Jugadores con amarillas acumuladas cerca del limite en el torneo actual (estimado)."""
    del_torneo = sorted([p for p in partidos if p["jugadores"] and p.get("torneo") == torneo
                         and equipo_id in (p["local"]["id"], p["visita"]["id"])], key=lambda p: p["fecha"])
    cuenta, ultimo = {}, {}
    for p in del_torneo:
        lado = "h" if p["local"]["id"] == equipo_id else "a"
        for j in p["jugadores"]:
            if j["lado"] != lado:
                continue
            cuenta.setdefault(j["id"], {"nombre": j["nombre"], "amarillas": 0})
            cuenta[j["id"]]["amarillas"] += j["amarillas"]
    if del_torneo:
        p = del_torneo[-1]
        lado = "h" if p["local"]["id"] == equipo_id else "a"
        ultimo = {j["id"]: j for j in p["jugadores"] if j["lado"] == lado}
    riesgo, suspendidos = [], []
    for jid, c in cuenta.items():
        a = int(c["amarillas"])
        u = ultimo.get(jid)
        if u and u["rojas"] > 0:
            suspendidos.append({"nombre": c["nombre"], "tipo": "Posible suspendido (roja último partido)"})
        elif u and u["amarillas"] > 0 and a > 0 and a % limite == 0:
            suspendidos.append({"nombre": c["nombre"], "tipo": f"Posible suspendido ({a} amarillas)"})
        elif a % limite == limite - 1:
            riesgo.append({"nombre": c["nombre"], "amarillas": a})
    return riesgo, suspendidos


def forma(partidos_todos, equipo_id, antes_de, n=5):
    previos = sorted([p for p in partidos_todos if equipo_id in (p["local"]["id"], p["visita"]["id"])
                      and p["fecha"] < antes_de], key=lambda p: p["fecha"])[-n:]
    salida = []
    for p in reversed(previos):
        es_local = p["local"]["id"] == equipo_id
        try:
            gf, gc = (int(p["goles"][0]), int(p["goles"][1])) if es_local else (int(p["goles"][1]), int(p["goles"][0]))
            res = "G" if gf > gc else "E" if gf == gc else "P"
        except (TypeError, ValueError):
            gf = gc = res = None
        rival = p["visita"] if es_local else p["local"]
        st = p.get("stats")
        lado = "h" if es_local else "a"
        salida.append({"fecha": p["fecha"], "rival": rival["nombre"], "logo": rival.get("logo"),
                       "condicion": "L" if es_local else "V", "gf": gf, "gc": gc, "res": res,
                       "tarjetas": st[lado]["tarjetas"] if st else None,
                       "corners": st[lado]["corners"] if st else None,
                       "faltan_datos": st is None})
    return salida


def h2h_propio(partidos, a, b):
    return [{"fecha": p["fecha"], "local": p["local"]["nombre"], "visita": p["visita"]["nombre"],
             "resultado": f"{p['goles'][0]} - {p['goles'][1]}",
             "tarjetas": (p["stats"]["h"]["tarjetas"] + p["stats"]["a"]["tarjetas"]) if p["stats"] else None,
             "corners": (p["stats"]["h"]["corners"] + p["stats"]["a"]["corners"]) if p["stats"] else None,
             "faltan_datos": p["stats"] is None}
            for p in sorted(partidos, key=lambda p: p["fecha"], reverse=True)
            if {p["local"]["id"], p["visita"]["id"]} == {a, b}]


def procesar(comp, ahora):
    hoy = ahora.astimezone(HORA_ARG).date()
    print(f"\n== {comp['nombre']} ==")
    eventos = calendario(comp, hoy)
    jugados = jugados_con_detalle(comp, eventos)
    con_stats = [p for p in jugados if p["stats"]]
    print(f"  {len(jugados)} jugados ({len(con_stats)} con estadísticas)")

    desde = datetime.combine(hoy, datetime.min.time(), HORA_ARG)
    hasta = desde + timedelta(days=DIAS_ADELANTE + 1)
    proximos = [e for e in eventos if e["estado"] != "post" and desde <= fecha_utc(e["fecha"]) < hasta]
    print(f"  {len(proximos)} partidos entre hoy y {DIAS_ADELANTE} días")
    fm = fotmob_partidos(comp, hoy, hoy + timedelta(days=DIAS_ADELANTE)) if proximos else []

    torneo = proximos[0]["torneo"] if proximos else None
    liga_tarjetas = (sum(p["stats"]["h"]["tarjetas"] + p["stats"]["a"]["tarjetas"] for p in con_stats) / len(con_stats)
                     if con_stats else None)
    liga_jugador = calculos.promedios_liga_jugador(jugados)
    resumen = []
    for ev in proximos:
        m = emparejar(ev, fm)
        extra = {}
        if m:
            try:
                extra = detalle_fotmob(m["id"])
            except Exception as err:
                print(f"  ! FotMob detalle {ev['local']['nombre']}-{ev['visita']['nombre']}: {err}")
        else:
            print(f"  ! sin FotMob para {ev['local']['nombre']} - {ev['visita']['nombre']}")
        hid, aid = ev["local"]["id"], ev["visita"]["id"]
        arbitro = extra.get("arbitro")
        analisis = calculos.analizar_partido(con_stats, hid, aid, ev["local"]["nombre"], ev["visita"]["nombre"], arbitro)

        bajas = {}
        for k, eid in (("local", hid), ("visita", aid)):
            riesgo, susp = riesgo_amarillas(jugados, eid, torneo, comp["amarillas_suspension"])
            fotmob_bajas = [{"nombre": b["nombre"], "tipo": TIPOS_BAJA.get(b["tipo"], b["tipo"] or "Baja"),
                             "vuelve": b.get("vuelve")} for b in (extra.get(k) or {}).get("bajas", [])]
            ya = {normalizar(b["nombre"] or "") for b in fotmob_bajas}
            fotmob_bajas += [s for s in susp if normalizar(s["nombre"]) not in ya]
            bajas[k] = {"bajas": fotmob_bajas, "riesgo": riesgo}

        jl = calculos.jugadores_equipo(jugados, hid, liga_jugador)
        jv = calculos.jugadores_equipo(jugados, aid, liga_jugador)
        for lista, k in ((jl, "local"), (jv, "visita")):
            tit = {normalizar(n) for n in (extra.get(k) or {}).get("titulares", [])}
            baja = {normalizar(b["nombre"] or "") for b in bajas[k]["bajas"]}
            for j in lista:
                j["en_once"] = normalizar(j["nombre"]) in tit
                j["baja"] = normalizar(j["nombre"]) in baja
            lista.sort(key=lambda j: (j["baja"], not j["en_once"], -j["titular"], -j["n"]))

        detalle = {
            "id": ev["id"], "competicion": comp["id"], "competicion_nombre": comp["nombre"],
            "fecha": ev["fecha"], "estado": ev["estado"],
            "local": ev["local"], "visita": ev["visita"],
            "estadio": extra.get("estadio") or ev["estadio"],
            "arbitro": arbitro, "promedio_tarjetas_liga": round(liga_tarjetas, 2) if liga_tarjetas else None,
            "alineacion_confirmada": extra.get("alineacion_confirmada", False),
            "tipo_alineacion": extra.get("tipo_alineacion"),
            "formaciones": {k: (extra.get(k) or {}).get("formacion") for k in ("local", "visita")},
            "analisis": analisis,
            "jugadores": {"local": jl[:18], "visita": jv[:18]},
            "bajas": bajas,
            "historial": {
                "h2h": extra.get("h2h") or [],
                "h2h_temporada": h2h_propio(jugados, hid, aid),
                "forma_local": forma(jugados, hid, ev["fecha"]),
                "forma_visita": forma(jugados, aid, ev["fecha"]),
            },
            "fotmob_id": m["id"] if m else None,
        }
        guardar(SALIDA / "partido" / f"{ev['id']}.json", detalle)
        resumen.append({
            "id": ev["id"], "competicion": comp["id"], "fecha": ev["fecha"], "estado": ev["estado"],
            "local": {k: ev["local"][k] for k in ("nombre", "logo")},
            "visita": {k: ev["visita"][k] for k in ("nombre", "logo")},
            "estadio": detalle["estadio"],
            "arbitro": arbitro["nombre"] if arbitro else None,
            "tarjetas_esperadas": analisis.get("tarjetas_esperadas"),
            "bajas": len(bajas["local"]["bajas"]) + len(bajas["visita"]["bajas"]),
            "alineacion_confirmada": detalle["alineacion_confirmada"],
            "pocos_datos": analisis["pocos_datos"],
        })
    return resumen


def main():
    ahora = datetime.now(timezone.utc)
    solo = sys.argv[1:]  # opcional: ids de competicion, ej. "arg"
    activas = [c for c in COMPETICIONES if (c["id"] in solo if solo else c["activa"])]
    previo = leer(SALIDA / "proximos.json", {}) or {}
    partidos = [p for p in previo.get("partidos", []) if p["competicion"] not in {c["id"] for c in activas}
                and fecha_utc(p["fecha"]) > ahora - timedelta(hours=3)]
    for comp in activas:
        try:
            partidos += procesar(comp, ahora)
        except Exception as err:
            print(f"  !! error en {comp['nombre']}: {err}")
            partidos += [p for p in previo.get("partidos", []) if p["competicion"] == comp["id"]]
    partidos.sort(key=lambda p: p["fecha"])
    guardar(SALIDA / "proximos.json", {
        "actualizado": ahora.isoformat(timespec="seconds"),
        "competiciones": [{"id": c["id"], "nombre": c["nombre"], "corto": c["corto"]}
                          for c in COMPETICIONES if c["activa"]],
        "partidos": partidos,
    })
    # borra detalles de partidos que ya no estan en la lista
    vigentes = {p["id"] for p in partidos}
    for f in (SALIDA / "partido").glob("*.json"):
        if f.stem not in vigentes:
            f.unlink()
    print(f"\nListo: {len(partidos)} partidos. Consultas: ESPN {fuentes.contador['espn']}, FotMob {fuentes.contador['fotmob']}")


if __name__ == "__main__":
    main()
