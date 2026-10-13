"""NBA: baja datos de ESPN, calcula promedios y lineas, y genera docs/data/nba/*.json.

Uso:
  python scripts/nba.py            actualizacion completa
  python scripts/nba.py --bajas    solo vuelve a leer los lesionados (rapido, cada 15 min)
"""
import math
import os
import re
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import fuentes
from actualizar import fecha_utc, guardar, leer
from config import CACHE, DIAS_ADELANTE, HORA_ARG, RAIZ

ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
SALIDA = RAIZ / "docs" / "data" / "nba"
CARPETA = CACHE / "nba"
PREVIOS_TEMPORADA_PASADA = 82  # temporada pasada completa como base hasta tener 5 partidos de la actual
MIN_PARTIDOS = 5
MIN_MINUTOS = 12               # jugadores con menos minutos promedio no se muestran

ESTADISTICAS = [("pts", "puntos"), ("reb", "rebotes"), ("ast", "asistencias"), ("tpm", "triples"),
                ("stl", "robos"), ("blk", "tapones")]

estado_fuentes = {}


def espn(ruta):
    try:
        data = fuentes.bajar(f"{ESPN}{ruta}", "espn")
        estado_fuentes.setdefault("ESPN", {"ok": True})
        return data
    except Exception as err:
        estado_fuentes["ESPN"] = {"ok": False, "error": str(err)[:120]}
        raise


# ---------------------------------------------------------------- partidos y calendario

def equipo(comp):
    t = comp["team"]
    logo = t.get("logo") or next((l["href"] for l in t.get("logos", []) if "dark" not in l.get("rel", [])), None)
    return {"id": t["id"], "nombre": t.get("shortDisplayName") or t["displayName"],
            "nombre_largo": t["displayName"], "abrev": t.get("abbreviation"), "logo": logo}


def puntos(comp):
    s = comp.get("score")
    s = s.get("displayValue") if isinstance(s, dict) else s
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def partido_compacto(e):
    c = e["competitions"][0]
    eq = {x["homeAway"]: x for x in c["competitors"]}
    return {"id": e["id"], "fecha": e["date"],
            "estado": (e.get("status") or c.get("status") or {}).get("type", {}).get("state"),
            "temporada": (e.get("season") or {}).get("year"), "tipo": (e.get("season") or {}).get("type"),
            "local": equipo(eq["home"]), "visita": equipo(eq["away"]),
            "puntos": [puntos(eq["home"]), puntos(eq["away"])],
            "estadio": (c.get("venue") or {}).get("fullName")}


def calendario_equipo(equipo_id, temporada, fija):
    """Partidos de temporada regular de un equipo. Las temporadas terminadas se cachean para siempre."""
    archivo = CARPETA / "calendarios" / f"{equipo_id}_{temporada}.json"
    if fija and (guardado := leer(archivo)) is not None:
        return guardado
    data = espn(f"/teams/{equipo_id}/schedule?season={temporada}&seasontype=2")
    lista = [partido_compacto(e) for e in data.get("events", [])]
    guardar(archivo, lista)
    return lista


def box_score(p):
    """Estadisticas por jugador de un partido jugado (cacheado: un partido terminado no cambia)."""
    archivo = CARPETA / "partidos" / f"{p['id']}.json"
    if (guardado := leer(archivo)) is not None:
        return guardado
    s = espn(f"/summary?event={p['id']}")
    jugadores = []
    for bloque in s.get("boxscore", {}).get("players", []):
        lado = "h" if bloque["team"]["id"] == p["local"]["id"] else "a"
        for st in bloque.get("statistics", [])[:1]:
            nombres = st.get("names") or st.get("labels") or []
            for a in st.get("athletes", []):
                if a.get("didNotPlay") or not a.get("stats"):
                    continue
                v = dict(zip(nombres, a["stats"]))
                try:
                    minutos = float(v.get("MIN") or 0)
                except ValueError:
                    minutos = 0
                if minutos <= 0:
                    continue
                num = lambda k: float(v.get(k) or 0) if str(v.get(k, "")).replace(".", "").lstrip("-").isdigit() else 0.0
                triples = str(v.get("3PT", "0-0")).split("-")[0]
                jugadores.append({"id": a["athlete"]["id"], "nombre": a["athlete"].get("displayName"), "lado": lado,
                                  "titular": bool(a.get("starter")), "min": minutos, "pts": num("PTS"),
                                  "reb": num("REB"), "ast": num("AST"), "tpm": float(triples or 0) if triples.isdigit() else 0.0,
                                  "stl": num("STL"), "blk": num("BLK")})
    datos = {**p, "jugadores": jugadores}
    guardar(archivo, datos)
    return datos


# ---------------------------------------------------------------- calculos

def normal_mas_de(media, desvio, linea):
    if desvio <= 0:
        return 1.0 if media > linea else 0.0
    return 0.5 * math.erfc((linea - media) / (desvio * math.sqrt(2)))


def poisson_mas_de(media, linea):
    if media <= 0:
        return 0.0
    return max(0.0, 1 - sum(math.exp(-media) * media ** k / math.factorial(k) for k in range(math.floor(linea) + 1)))


def prob_mas_de(valores, media, linea):
    """Para estadisticas chicas (robos, triples) Poisson; para las grandes (puntos) normal con el desvio real."""
    if media < 8:
        return poisson_mas_de(media, linea)
    desvio = statistics.pstdev(valores) if len(valores) >= 8 else 0.35 * media + 1.5
    return normal_mas_de(media, max(desvio, 1.0), linea)


def lineas_para(media, stat):
    """Lineas parecidas a las que ofrecen las casas: alrededor del promedio."""
    paso = {"pts": 3, "reb": 2, "ast": 2}.get(stat)
    if stat == "tpm":
        return [l for l in (0.5, 1.5, 2.5, 3.5, 4.5) if media - 1.5 <= l <= media + 1.5][:3] or [0.5]
    if stat in ("stl", "blk"):
        return [0.5, 1.5]
    centro = math.floor(media) + 0.5
    return sorted({max(0.5, centro - paso), centro, centro + paso})


def txt(n):
    return f"{n:.1f}".replace(".", ",")


def stats_jugador(juegos):
    """juegos: lista de dicts (mas viejo primero)."""
    n = len(juegos)
    prom = {k: sum(j[k] for j in juegos) / n for k in ("min", "pts", "reb", "ast", "tpm", "stl", "blk")}
    return n, prom


def analizar_jugadores(equipo_id, roster, juegos_por_jugador, temporada_actual, bajas):
    salida = []
    for jid, nombre, pos in roster:
        juegos = sorted(juegos_por_jugador.get(jid, []), key=lambda j: j["fecha"])
        if not juegos:
            continue
        actuales = [j for j in juegos if j["temporada"] == temporada_actual]
        base = actuales if len(actuales) >= MIN_PARTIDOS else juegos[-PREVIOS_TEMPORADA_PASADA:]
        n, prom = stats_jugador(base)
        if prom["min"] < MIN_MINUTOS:
            continue
        n5, prom5 = stats_jugador(juegos[-5:])
        mercados = []
        for stat, nombre_stat in ESTADISTICAS:
            # linea: 60% promedio de la temporada + 40% ultimos 5 (los ultimos 5 de la temporada
            # pasada no cuentan: al final de la temporada muchas figuras descansan)
            media = 0.6 * prom[stat] + 0.4 * prom5[stat] if len(actuales) >= MIN_PARTIDOS else prom[stat]
            valores = [j[stat] for j in base]
            for linea in lineas_para(media, stat):
                p = prob_mas_de(valores, media, linea)
                if 0.08 < p < 0.92:  # las lineas casi seguras o casi imposibles no aportan
                    mercados.append({"stat": stat, "nombre": f"Más de {txt(linea)} {nombre_stat}",
                                     "linea": linea, "prob": round(p, 3)})
        salida.append({
            "id": jid, "nombre": nombre, "pos": pos, "n": n, "pocos_datos": n < MIN_PARTIDOS,
            "base": "temporada" if len(actuales) >= MIN_PARTIDOS else "temporada pasada",
            "prom": {k: round(v, 1) for k, v in prom.items()},
            "prom5": {k: round(v, 1) for k, v in prom5.items()},
            "baja": bajas.get(jid, {}).get("estado"),
            "mercados": mercados,
        })
    salida.sort(key=lambda j: (j["baja"] == "Descartado", -j["prom"]["min"]))
    return salida


def promedios_equipo(juegos, equipo_id, temporada_actual):
    """Puntos a favor y en contra, de local y visitante."""
    jugados = [p for p in juegos if p["estado"] == "post" and p["puntos"][0] is not None]
    actuales = [p for p in jugados if p["temporada"] == temporada_actual]
    base = actuales if len(actuales) >= 2 * MIN_PARTIDOS else jugados[-max(PREVIOS_TEMPORADA_PASADA * 2, len(actuales)):]
    res = {"base": "temporada" if base is actuales else "incluye temporada pasada"}
    for cond, lado, rival in (("local", 0, 1), ("visita", 1, 0)):
        key = "local" if cond == "local" else "visita"
        ps = [p for p in base if p[key]["id"] == equipo_id]
        res[cond] = {"n": len(ps),
                     "favor": round(sum(p["puntos"][lado] for p in ps) / len(ps), 1) if ps else None,
                     "contra": round(sum(p["puntos"][rival] for p in ps) / len(ps), 1) if ps else None}
    return res


def forma(juegos, equipo_id, antes_de, n=5):
    previos = [p for p in juegos if p["estado"] == "post" and p["fecha"] < antes_de and p["puntos"][0] is not None][-n:]
    salida = []
    for p in reversed(previos):
        local = p["local"]["id"] == equipo_id
        pf, pc = (p["puntos"][0], p["puntos"][1]) if local else (p["puntos"][1], p["puntos"][0])
        rival = p["visita"] if local else p["local"]
        salida.append({"fecha": p["fecha"], "rival": rival["nombre"], "logo": rival["logo"],
                       "condicion": "L" if local else "V", "pf": pf, "pc": pc, "res": "G" if pf > pc else "P"})
    return salida


# ---------------------------------------------------------------- lesionados

def id_desde_links(athlete):
    for l in athlete.get("links", []):
        m = re.search(r"/id/(\d+)", l.get("href", ""))
        if m:
            return m.group(1)
    return None


def leer_bajas():
    """Lesionados de toda la liga, agrupados por equipo."""
    data = espn("/injuries")
    por_equipo = {}
    for t in data.get("injuries", []):
        lista = []
        for i in t.get("injuries", []):
            comentario = f"{i.get('shortComment', '')} {i.get('longComment', '')}".lower()
            det = i.get("details") or {}
            if (det.get("type") or "").lower() == "rest" or "(rest)" in comentario or "rest " in comentario[:60] or "load management" in comentario:
                estado = "Descansa"
            elif i.get("status") == "Out":
                estado = "Descartado"
            else:
                estado = "Dudoso"
            lista.append({"id": id_desde_links(i.get("athlete", {})), "nombre": i.get("athlete", {}).get("displayName"),
                          "estado": estado, "motivo": det.get("type") or "", "vuelve": det.get("returnDate"),
                          "comentario": i.get("shortComment", "")[:200]})
        por_equipo[str(t.get("id"))] = lista
    return por_equipo


# ---------------------------------------------------------------- armado

def partidos_ventana(hoy):
    eventos = {}
    for d in range(-1, DIAS_ADELANTE + 1):
        dia = hoy + timedelta(days=d)
        for e in espn(f"/scoreboard?dates={dia:%Y%m%d}").get("events", []):
            eventos[e["id"]] = partido_compacto(e)
    desde = datetime.combine(hoy, datetime.min.time(), HORA_ARG)
    hasta = desde + timedelta(days=DIAS_ADELANTE + 1)
    # solo temporada regular (2) y playoffs (3); la pretemporada no se analiza
    return sorted([e for e in eventos.values() if e["estado"] != "post" and e["tipo"] in (2, 3)
                   and desde <= fecha_utc(e["fecha"]) < hasta], key=lambda e: e["fecha"])


def total_mercados(esperado, desvio, centro_paso, nombre):
    centro = math.floor(esperado) + 0.5
    return [{"nombre": f"Más de {txt(l)} {nombre}", "linea": l, "prob": round(normal_mas_de(esperado, desvio, l), 3)}
            for l in (centro - 2 * centro_paso, centro - centro_paso, centro, centro + centro_paso, centro + 2 * centro_paso)]


def completo(ahora):
    hoy = ahora.astimezone(HORA_ARG).date()
    if os.environ.get("NBA_HOY"):  # solo para pruebas: simular otro dia
        hoy = datetime.strptime(os.environ["NBA_HOY"], "%Y-%m-%d").date()
    proximos = partidos_ventana(hoy)
    print(f"NBA: {len(proximos)} partidos entre hoy y {DIAS_ADELANTE} días")
    if not proximos:
        return []
    temporada_actual = proximos[0]["temporada"] if proximos else None
    equipos = sorted({p[k]["id"] for p in proximos for k in ("local", "visita")})

    def preparar(eid):
        anterior = calendario_equipo(eid, temporada_actual - 1, fija=True)
        actual = calendario_equipo(eid, temporada_actual, fija=False)
        jugados_ant = [p for p in anterior if p["estado"] == "post"][-PREVIOS_TEMPORADA_PASADA:]
        jugados_act = [p for p in actual if p["estado"] == "post"]
        roster = espn(f"/teams/{eid}/roster").get("athletes", [])
        return eid, anterior + actual, jugados_ant + jugados_act, [
            (a["id"], a.get("displayName"), (a.get("position") or {}).get("abbreviation")) for a in roster]

    datos_equipo = {}
    with ThreadPoolExecutor(4) as pool:
        for eid, calendario, para_box, roster in pool.map(preparar, equipos):
            datos_equipo[eid] = {"calendario": sorted(calendario, key=lambda p: p["fecha"]), "box": para_box, "roster": roster}
    todos_box = {p["id"]: p for d in datos_equipo.values() for p in d["box"]}
    faltan = [p for p in todos_box.values() if not (CARPETA / "partidos" / f"{p['id']}.json").exists()]
    if faltan:
        print(f"  bajando {len(faltan)} box scores...")
    with ThreadPoolExecutor(4) as pool:
        boxes = [b for b in pool.map(lambda p: _seguro(box_score, p), todos_box.values()) if b]

    juegos_por_jugador = {}
    for b in boxes:
        for j in b["jugadores"]:
            juegos_por_jugador.setdefault(j["id"], []).append({**j, "fecha": b["fecha"], "temporada": b["temporada"]})

    bajas = leer_bajas()
    resumen = []
    for p in proximos:
        hid, aid = p["local"]["id"], p["visita"]["id"]
        cal_h, cal_a = datos_equipo[hid]["calendario"], datos_equipo[aid]["calendario"]
        bh = {b["id"]: b for b in bajas.get(hid, [])}
        ba = {b["id"]: b for b in bajas.get(aid, [])}
        eh = promedios_equipo(cal_h, hid, temporada_actual)
        ea = promedios_equipo(cal_a, aid, temporada_actual)
        cruce = lambda a, b: round((a + b) / 2, 1) if a is not None and b is not None else (a or b)
        esp_h = cruce(eh["local"]["favor"], ea["visita"]["contra"])
        esp_a = cruce(ea["visita"]["favor"], eh["local"]["contra"])
        equipos_tab = None
        if esp_h and esp_a:
            total = esp_h + esp_a
            equipos_tab = {
                "promedios": {"local": eh, "visita": ea},
                "esperado": {"local": esp_h, "visita": esp_a, "total": round(total, 1)},
                "grupos": [
                    {"titulo": "Total del partido", "mercados": total_mercados(total, 18, 4, "puntos")},
                    {"titulo": p["local"]["nombre"], "mercados": total_mercados(esp_h, 12, 3, f"puntos - {p['local']['nombre']}")},
                    {"titulo": p["visita"]["nombre"], "mercados": total_mercados(esp_a, 12, 3, f"puntos - {p['visita']['nombre']}")},
                ],
                "pocos_datos": min(eh["local"]["n"], ea["visita"]["n"]) < MIN_PARTIDOS,
            }
        h2h = [x for x in {q["id"]: q for q in cal_h + cal_a}.values()
               if {x["local"]["id"], x["visita"]["id"]} == {hid, aid} and x["estado"] == "post" and x["puntos"][0] is not None]
        h2h.sort(key=lambda x: x["fecha"], reverse=True)
        detalle = {
            "id": p["id"], "deporte": "nba", "fecha": p["fecha"], "estado": p["estado"],
            "local": p["local"], "visita": p["visita"], "estadio": p["estadio"],
            "temporada": temporada_actual,
            "jugadores": {
                "local": analizar_jugadores(hid, datos_equipo[hid]["roster"], juegos_por_jugador, temporada_actual, bh),
                "visita": analizar_jugadores(aid, datos_equipo[aid]["roster"], juegos_por_jugador, temporada_actual, ba),
            },
            "equipos": equipos_tab,
            "bajas": {"local": bajas.get(hid, []), "visita": bajas.get(aid, [])},
            "historial": {
                "h2h": [{"fecha": x["fecha"], "local": x["local"]["nombre"], "visita": x["visita"]["nombre"],
                         "resultado": f"{x['puntos'][0]} - {x['puntos'][1]}"} for x in h2h[:6]],
                "forma_local": forma(cal_h, hid, p["fecha"]),
                "forma_visita": forma(cal_a, aid, p["fecha"]),
            },
        }
        guardar(SALIDA / "partido" / f"{p['id']}.json", detalle)
        resumen.append(resumen_partido(detalle))
    return resumen


def resumen_partido(d):
    return {"id": d["id"], "fecha": d["fecha"], "estado": d["estado"],
            "local": {k: d["local"][k] for k in ("nombre", "logo")},
            "visita": {k: d["visita"][k] for k in ("nombre", "logo")},
            "estadio": d["estadio"],
            "total_esperado": (d["equipos"] or {}).get("esperado", {}).get("total"),
            "bajas": sum(1 for k in ("local", "visita") for b in d["bajas"][k] if b["estado"] != "Dudoso"),
            "dudosos": sum(1 for k in ("local", "visita") for b in d["bajas"][k] if b["estado"] == "Dudoso")}


def _seguro(funcion, *args):
    try:
        return funcion(*args)
    except Exception as err:
        print(f"  ! {err}")
        return None


def solo_bajas():
    """Modo rapido: actualiza los lesionados de los partidos ya armados."""
    indice = leer(SALIDA / "proximos.json")
    if not indice or not indice.get("partidos"):
        return
    bajas = leer_bajas()
    for p in indice["partidos"]:
        archivo = SALIDA / "partido" / f"{p['id']}.json"
        d = leer(archivo)
        if not d:
            continue
        d["bajas"] = {"local": bajas.get(d["local"]["id"], []), "visita": bajas.get(d["visita"]["id"], [])}
        for k in ("local", "visita"):
            por_id = {b["id"]: b["estado"] for b in d["bajas"][k]}
            for j in d["jugadores"][k]:
                j["baja"] = por_id.get(j["id"])
        guardar(archivo, d)
        p.update(resumen_partido(d))
    indice["fuentes"] = estado_fuentes
    guardar(SALIDA / "proximos.json", indice)
    print("NBA: lesionados actualizados")


def main():
    ahora = datetime.now(timezone.utc)
    if "--bajas" in sys.argv:
        try:
            solo_bajas()
        except Exception as err:
            print(f"!! NBA bajas: {err}")
        return
    previo = leer(SALIDA / "proximos.json", {}) or {}
    try:
        partidos = completo(ahora)
        actualizado = ahora.isoformat(timespec="seconds")
    except Exception as err:
        # si ESPN no responde se dejan los datos anteriores y la pagina avisa
        print(f"!! NBA: {err}")
        estado_fuentes.setdefault("ESPN", {"ok": False, "error": str(err)[:120]})
        partidos = [p for p in previo.get("partidos", []) if fecha_utc(p["fecha"]) > ahora - timedelta(hours=3)]
        actualizado = previo.get("actualizado")
    guardar(SALIDA / "proximos.json", {"actualizado": actualizado, "revisado": ahora.isoformat(timespec="seconds"),
                                       "fuentes": estado_fuentes, "partidos": partidos})
    vigentes = {p["id"] for p in partidos}
    for f in (SALIDA / "partido").glob("*.json"):
        if f.stem not in vigentes:
            f.unlink()
    print(f"Listo NBA: {len(partidos)} partidos. Consultas ESPN: {fuentes.contador['espn']}")


if __name__ == "__main__":
    main()
