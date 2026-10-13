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


# ---------------------------------------------------------------- documentos de la FIA

FIA = "https://www.fia.com"
FIA_LISTA = f"{FIA}/documents/championships/fia-formula-one-world-championship-14"
MOTIVOS = {"performance - local load": "Rendimiento: más carga en la zona",
           "performance - flow conditioning": "Rendimiento: mejor flujo de aire",
           "performance - drag reduction": "Rendimiento: menos resistencia",
           "circuit specific - cooling range": "Para este circuito: refrigeración",
           "circuit specific - balance range": "Para este circuito: balance aerodinámico",
           "reliability": "Fiabilidad"}
RE_MEJORA = re.compile(r"(?:^|\s)(\d{1,2})\s+([A-Z][A-Za-z /&-]{2,40}?)\s+"
                       r"(Performance\s*-\s*(?:Local Load|Flow Conditioning|Drag Reduction)|"
                       r"Circuit specific\s*-\s*(?:Cooling Range|Balance Range)|Reliability)", re.I)


def texto_web(url):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": fuentes.UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            datos = r.read()
        estado_fuentes.setdefault("FIA", {"ok": True})
        return datos
    except Exception as err:
        estado_fuentes["FIA"] = {"ok": False, "error": str(err)[:120]}
        raise


def texto_pdf(url):
    """Texto de un PDF de la FIA. Se cachea: un documento publicado no cambia."""
    archivo = CARPETA / "fia" / f"{hashlib.sha1(url.encode()).hexdigest()[:16]}.json"
    if (guardado := leer(archivo)) is not None:
        return guardado["texto"]
    import io
    import pypdf
    lector = pypdf.PdfReader(io.BytesIO(texto_web(url)))
    texto = "\n".join(p.extract_text() or "" for p in lector.pages)
    guardar(archivo, {"url": url, "texto": texto})
    return texto


def campo(texto, nombre, hasta):
    texto = texto.replace(" ", " ")  # los PDF de la FIA usan espacios duros
    m = re.search(rf"\n{nombre}\s+(.+?)\n(?:{hasta})\s", texto, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def tipo_decision(decision):
    d = (decision or "").lower()
    if not d or "no penalty" in d or "no further action" in d or "no action" in d:
        return "sin sanción"
    if "disqualif" in d:
        return "descalificado"
    if "grid" in d or "pit lane" in d or "back of the" in d:
        return "grilla"
    if "drive through" in d or "drive-through" in d or "stop and go" in d or "second time penalty" in d or "time penalty" in d:
        return "penalización"
    if "reprimand" in d:
        return "reprimenda"
    if "fine" in d or "€" in d:
        return "multa"
    if "warning" in d:
        return "advertencia"
    return "otra"


def traducir_decision(decision):
    """Traduce las decisiones mas comunes de los comisarios; si no reconoce la frase, la deja en ingles."""
    if not decision:
        return None
    d = decision.strip().rstrip(".")
    reglas = [
        (r"required to start the race from the pit lane", "Larga la carrera desde el pit lane"),
        (r"required to start the sprint from the pit lane", "Larga el sprint desde el pit lane"),
        (r"drop of (\d+) grid positions? in the next race.*", r"Pierde \1 puestos en la grilla de la próxima carrera"),
        (r"drop of (\d+) grid positions? .*sprint.*", r"Pierde \1 puestos en la grilla del sprint"),
        (r"drop of (\d+) grid positions?.*", r"Pierde \1 puestos en la grilla"),
        (r"(\d+) grid place penalty.*", r"Pierde \1 puestos en la grilla"),
        (r"(\d+) second time penalty.*", r"Penalización de \1 segundos"),
        (r"drive[- ]through penalty.*", "Penalización de drive-through"),
        (r"(\d+) second stop and go penalty.*", r"Stop and go de \1 segundos"),
        (r"disqualified.*", "Descalificado"),
        (r"reprimand.*", "Reprimenda"),
        (r"(?:driver: )?warning.*", "Advertencia"),
        (r"no (?:penalty|further action).*", "Sin sanción"),
        (r"start from the back of the grid.*", "Larga desde el fondo de la grilla"),
    ]
    for patron, es in reglas:
        if re.fullmatch(patron, d, re.I):
            extra = re.search(r"(\d+) penalty points?", decision, re.I)
            texto = re.sub(patron, es, d, flags=re.I)
            return texto + (f" y {extra.group(1)} puntos de penalización" if extra and "puntos" not in texto else "")
    return decision


def leer_mejoras(texto):
    """Car Presentation Submissions: mejoras que declara cada equipo. El formato cambia segun el equipo,
    asi que se busca cada item por los motivos fijos del formulario de la FIA."""
    equipos = []
    for bloque in re.split(r"Car Presentation\s*[–-]\s*", texto)[1:]:
        lineas = [l.strip() for l in bloque.splitlines() if l.strip()]
        if len(lineas) < 2:
            continue
        equipo = lineas[1]
        cuerpo = " ".join(lineas[2:])
        if re.search(r"no updates?\b", cuerpo, re.I) and not RE_MEJORA.search(cuerpo):
            equipos.append({"equipo": equipo, "mejoras": [], "leido": True})
            continue
        items = list(RE_MEJORA.finditer(cuerpo))
        mejoras = []
        for i, m in enumerate(items):
            fin = items[i + 1].start() if i + 1 < len(items) else len(cuerpo)
            detalle = re.sub(r"\s+", " ", cuerpo[m.end():fin]).strip()
            motivo = re.sub(r"\s+", " ", m.group(3)).strip()
            mejoras.append({"componente": m.group(2).strip().title(), "motivo": MOTIVOS.get(motivo.lower(), motivo),
                            "detalle": detalle[:400]})
        equipos.append({"equipo": equipo, "mejoras": mejoras, "leido": bool(mejoras)})
    return equipos


def documentos_fia(codigo_por_numero):
    """Lee la lista de documentos del ultimo Gran Premio en fia.com: decisiones de los comisarios y mejoras."""
    pagina = texto_web(FIA_LISTA).decode("utf-8", "ignore")
    evento = re.search(r'<div class="event-title active">\s*([^<]+?)\s*</div>', pagina)
    filas = re.findall(r'<a href="(/system/files/decision-document/[^"]+\.pdf)".*?<div class="title">\s*(.+?)\s*</div>'
                       r'.*?date-display-single">([^<]+)<', pagina, re.S)
    sanciones, mejoras = [], None
    for href, titulo, publicado in filas:
        titulo = re.sub(r"\s+", " ", titulo)
        url = FIA + href
        try:
            if re.search(r"Car Presentation Submissions", titulo, re.I):
                mejoras = {"titulo": titulo, "url": url, "publicado": publicado, "equipos": leer_mejoras(texto_pdf(url))}
            elif re.search(r"(Infringement|Decision|Offence) - Car \d+", titulo, re.I):
                texto = texto_pdf(url)
                decision = campo(texto, "Decision", "Reason|Competitors")
                piloto = campo(texto, r"No / Driver", "Competitor")
                numero = re.match(r"(\d+)", piloto or "")
                sanciones.append({
                    "id": hashlib.sha1(url.encode()).hexdigest()[:12], "titulo": titulo, "url": url, "publicado": publicado,
                    "piloto": re.sub(r"^\d+\s*-\s*", "", piloto or "") or None,
                    "codigo": codigo_por_numero.get(numero.group(1)) if numero else None,
                    "sesion": campo(texto, "Session", "Fact"), "hecho": campo(texto, "Fact", "Infringement"),
                    "decision": decision, "decision_es": traducir_decision(decision), "tipo": tipo_decision(decision),
                    "proxima_carrera": bool(re.search(r"next (race|event|competition)", decision or "", re.I)),
                })
        except Exception as err:
            print(f"  ! FIA {titulo}: {err}")
    return {"evento": evento.group(1) if evento else None, "url": FIA_LISTA, "sanciones": sanciones, "mejoras": mejoras}


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
    numeros = {x["number"]: x["Driver"].get("code") for r in carreras for x in r["Results"]}
    fia = leer_fia(numeros)
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
        "numeros": numeros,
        "fia": fia,
    }


def leer_fia(numeros):
    try:
        return documentos_fia(numeros)
    except Exception as err:
        print(f"  ! FIA: {err}")
        return (leer(SALIDA / "gp.json", {}) or {}).get("fia")


def solo_sanciones(ahora):
    """Modo rapido: solo durante el fin de semana de carrera (y hasta 2 dias despues)."""
    datos = leer(SALIDA / "gp.json")
    if not datos or not datos.get("gp"):
        return
    inicio = fecha_utc(datos["gp"]["sesiones"][0]["fecha"])
    fin = fecha_utc(datos["gp"]["sesiones"][-1]["fecha"])
    # desde el jueves (ahi la FIA publica las mejoras de cada equipo) hasta 2 dias despues de la carrera
    if not (inicio - timedelta(hours=36) <= ahora <= fin + timedelta(days=2)):
        print("F1: no es fin de semana de carrera, no se revisan sanciones")
        return
    codigos = {p["codigo"]: p["nombre"] for p in datos["pilotos"] if p["codigo"]}
    datos["fia"] = leer_fia(datos.get("numeros", {}))
    try:
        todas = sesiones_openf1(datos["temporada"])
        datos["sanciones"] = sanciones_de(sesiones_relevantes(todas, inicio, ahora), codigos)
    except Exception as err:
        print(f"  ! OpenF1: {err}")
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
