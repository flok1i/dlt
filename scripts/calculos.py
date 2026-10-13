"""Promedios, ajuste por arbitro y probabilidades con Poisson."""
import math

from config import LINEAS, MIN_PARTIDOS

METRICAS = ["tarjetas", "corners", "faltas", "remates", "remates_arco"]


def poisson_mas_de(media, linea):
    """Probabilidad de que salgan MAS de `linea` (ej. 4.5 -> 5 o mas)."""
    if media <= 0:
        return 0.0
    k_max = math.floor(linea)
    acumulada = sum(math.exp(-media) * media ** k / math.factorial(k) for k in range(k_max + 1))
    return max(0.0, min(1.0, 1 - acumulada))


def _prom(valores):
    return sum(valores) / len(valores) if valores else None


def promedios_equipo(partidos, equipo_id):
    """Promedios a favor y en contra, separados de local y visitante.
    `partidos` = partidos jugados con estadisticas (formato compacto de cache)."""
    res = {}
    for condicion in ("local", "visita"):
        lado, rival = ("h", "a") if condicion == "local" else ("a", "h")
        jugados = [p for p in partidos if p["stats"] and p[condicion]["id"] == equipo_id]
        res[condicion] = {
            "n": len(jugados),
            "favor": {m: _prom([p["stats"][lado][m] for p in jugados]) for m in METRICAS},
            "contra": {m: _prom([p["stats"][rival][m] for p in jugados]) for m in METRICAS},
        }
    todos = [(p, "h" if p["local"]["id"] == equipo_id else "a") for p in partidos
             if p["stats"] and equipo_id in (p["local"]["id"], p["visita"]["id"])]
    res["total"] = {
        "n": len(todos),
        "favor": {m: _prom([p["stats"][l][m] for p, l in todos]) for m in METRICAS},
        "contra": {m: _prom([p["stats"]["a" if l == "h" else "h"][m] for p, l in todos]) for m in METRICAS},
    }
    return res


def _cruce(ataque, defensa, ataque_total, defensa_total):
    """Promedio entre lo que hace un equipo y lo que concede el rival.
    Si un lado tiene menos de 3 partidos, usa el total de la temporada."""
    a = ataque if ataque is not None else ataque_total
    d = defensa if defensa is not None else defensa_total
    vals = [v for v in (a, d) if v is not None]
    return _prom(vals)


def esperado(prom_local, prom_visita, metrica):
    def elegir(p, cond, lado):
        return p[cond][lado][metrica] if p[cond]["n"] >= 3 else None
    h = _cruce(elegir(prom_local, "local", "favor"), elegir(prom_visita, "visita", "contra"),
               prom_local["total"]["favor"][metrica], prom_visita["total"]["contra"][metrica])
    a = _cruce(elegir(prom_visita, "visita", "favor"), elegir(prom_local, "local", "contra"),
               prom_visita["total"]["favor"][metrica], prom_local["total"]["contra"][metrica])
    return h, a


def linea_txt(linea):
    return f"{linea:.1f}".replace(".", ",")


def mercados(nombre, media, lineas, sufijo=""):
    if media is None:
        return []
    return [{"nombre": f"Más de {linea_txt(l)} {nombre}{sufijo}", "linea": l,
             "prob": round(poisson_mas_de(media, l), 3)} for l in lineas]


def factor_arbitro(arbitro):
    """Promedio de amarillas del arbitro dividido el de la competicion (de FotMob)."""
    if not arbitro or not arbitro.get("amarillas") or not arbitro.get("amarillas_liga"):
        return 1.0
    return max(0.7, min(1.4, arbitro["amarillas"] / arbitro["amarillas_liga"]))


def analizar_partido(partidos, local, visita, nombre_local, nombre_visita, arbitro):
    pl, pv = promedios_equipo(partidos, local), promedios_equipo(partidos, visita)
    pocos = min(pl["local"]["n"], pv["visita"]["n"]) < MIN_PARTIDOS
    factor = factor_arbitro(arbitro)
    out = {"pocos_datos": pocos, "factor_arbitro": round(factor, 2),
           "partidos_local": pl["local"]["n"], "partidos_visita": pv["visita"]["n"], "tabs": {}}

    for metrica, etiqueta in (("tarjetas", "tarjetas"), ("corners", "córners"), ("faltas", "faltas")):
        h, a = esperado(pl, pv, metrica)
        if h is None or a is None:
            out["tabs"][metrica] = None
            continue
        if metrica == "tarjetas":
            h, a = h * factor, a * factor
        total = h + a
        out["tabs"][metrica] = {
            "esperado": {"total": round(total, 2), "local": round(h, 2), "visita": round(a, 2)},
            "promedios": {
                "local": {"favor": pl["local"]["favor"][metrica], "contra": pl["local"]["contra"][metrica],
                          "n": pl["local"]["n"]},
                "visita": {"favor": pv["visita"]["favor"][metrica], "contra": pv["visita"]["contra"][metrica],
                           "n": pv["visita"]["n"]},
            },
            "grupos": [
                {"titulo": "Total del partido", "mercados": mercados(etiqueta, total, LINEAS[metrica])},
                {"titulo": nombre_local, "mercados": mercados(etiqueta, h, LINEAS[f"{metrica}_equipo"], f" - {nombre_local}")},
                {"titulo": nombre_visita, "mercados": mercados(etiqueta, a, LINEAS[f"{metrica}_equipo"], f" - {nombre_visita}")},
            ],
        }
    if out["tabs"].get("tarjetas"):
        out["tarjetas_esperadas"] = out["tabs"]["tarjetas"]["esperado"]["total"]
    return out


STATS_JUGADOR = ("remates", "remates_arco", "faltas", "amarillas", "atajadas")
PESO_LIGA = 3  # equivale a sumarle 3 partidos "promedio de la liga" a cada jugador


def promedios_liga_jugador(partidos):
    """Promedio por partido de un jugador de campo y de un arquero en toda la liga."""
    suma = {"campo": dict.fromkeys(STATS_JUGADOR, 0.0), "G": dict.fromkeys(STATS_JUGADOR, 0.0)}
    n = {"campo": 0, "G": 0}
    for p in partidos:
        for j in p["jugadores"] or []:
            if not j["titular"]:
                continue
            k = "G" if j["pos"] == "G" else "campo"
            n[k] += 1
            for m in STATS_JUGADOR:
                suma[k][m] += j[m]
    return {k: {m: suma[k][m] / n[k] if n[k] else 0 for m in STATS_JUGADOR} for k in suma}


def jugadores_equipo(partidos, equipo_id, liga=None, ultimos=10):
    """Promedios por jugador en los ultimos `ultimos` partidos del equipo,
    suavizados hacia el promedio de la liga para que pocos partidos no den 0% o 100%."""
    del_equipo = [p for p in partidos if p["jugadores"] and equipo_id in (p["local"]["id"], p["visita"]["id"])]
    del_equipo = sorted(del_equipo, key=lambda p: p["fecha"])[-ultimos:]
    acum = {}
    for p in del_equipo:
        lado = "h" if p["local"]["id"] == equipo_id else "a"
        for j in p["jugadores"]:
            if j["lado"] != lado or not j["jugo"]:
                continue
            a = acum.setdefault(j["id"], {"id": j["id"], "nombre": j["nombre"], "pos": j["pos"], "n": 0, "titular": 0,
                                          "remates": 0, "remates_arco": 0, "faltas": 0, "amarillas": 0, "atajadas": 0})
            if j["pos"] == "G":  # los suplentes vienen como "SUB"; si alguna vez ataja, es arquero
                a["pos"] = "G"
            elif a["pos"] == "SUB" and j["pos"] != "SUB":
                a["pos"] = j["pos"]
            a["n"] += 1
            a["titular"] += 1 if j["titular"] else 0
            for m in ("remates", "remates_arco", "faltas", "amarillas", "atajadas"):
                a[m] += j[m]
    salida = []
    for a in acum.values():
        n = a["n"]
        base = (liga or {}).get("G" if a["pos"] == "G" else "campo")
        if base:
            prom = {m: (a[m] + base[m] * PESO_LIGA) / (n + PESO_LIGA) for m in STATS_JUGADOR}
        else:
            prom = {m: a[m] / n for m in STATS_JUGADOR}
        merc = [
            ("Remates: más de 0,5", poisson_mas_de(prom["remates"], 0.5)),
            ("Remates: más de 1,5", poisson_mas_de(prom["remates"], 1.5)),
            ("Al arco: más de 0,5", poisson_mas_de(prom["remates_arco"], 0.5)),
            ("Faltas: más de 0,5", poisson_mas_de(prom["faltas"], 0.5)),
            ("Faltas: más de 1,5", poisson_mas_de(prom["faltas"], 1.5)),
            ("Tarjeta", poisson_mas_de(prom["amarillas"], 0.5)),
        ]
        if a["pos"] == "G":
            merc = [("Atajadas: más de 1,5", poisson_mas_de(prom["atajadas"], 1.5)),
                    ("Atajadas: más de 2,5", poisson_mas_de(prom["atajadas"], 2.5)),
                    ("Atajadas: más de 3,5", poisson_mas_de(prom["atajadas"], 3.5))]
        salida.append({"id": a["id"], "nombre": a["nombre"], "pos": a["pos"], "n": n, "titular": a["titular"],
                       "pocos_datos": n < MIN_PARTIDOS,
                       "prom": {k: round(v, 2) for k, v in prom.items()},
                       "mercados": [{"nombre": nm, "prob": round(pr, 3)} for nm, pr in merc]})
    salida.sort(key=lambda x: (-x["titular"], -x["n"]))
    return salida
