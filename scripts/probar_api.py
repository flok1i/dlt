r"""Prueba la clave de API-Football y revisa si la temporada actual de cada
competicion de DLT esta disponible en el plan gratis.

Uso: python scripts\probar_api.py
La clave se lee de la variable API_FOOTBALL_KEY; si no esta, la pide sin mostrarla.
Gasta como maximo 7 consultas (1 de /leagues + 1 de /fixtures por competicion).
"""
import getpass
import json
import os
import urllib.parse
import urllib.request

BASE = "https://v3.football.api-sports.io"
COMPETICIONES = {
    128: "Liga Profesional Argentina",
    71: "Brasileirao Serie A",
    2: "Champions League",
    3: "Europa League",
    13: "Copa Libertadores",
    11: "Copa Sudamericana",
}


def consultar(clave, ruta, **params):
    url = f"{BASE}{ruta}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"x-apisports-key": clave})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def leer_clave():
    if os.environ.get("API_FOOTBALL_KEY"):
        return os.environ["API_FOOTBALL_KEY"].strip()
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            for linea in f:
                if linea.startswith("API_FOOTBALL_KEY="):
                    return linea.split("=", 1)[1].strip()
    while True:
        clave = getpass.getpass("Pega tu clave con CLIC DERECHO (no se ve al escribir) y Enter: ").strip()
        if len(clave) >= 20 and clave.isalnum():
            break
        print("Eso no parece una clave (quiza se pego mal). Proba de nuevo con clic derecho.")
    with open(ENV_FILE, "a", encoding="utf-8") as f:
        f.write(f"API_FOOTBALL_KEY={clave}\n")
    print("Clave guardada en .env (privado, no se sube a GitHub).")
    return clave


def main():
    clave = leer_clave()

    status = consultar(clave, "/status")  # /status no descuenta consultas
    if status.get("errors"):
        print("ERROR con la clave:", status["errors"])
        return
    r = status["response"]
    print(f"Cuenta OK - plan: {r['subscription']['plan']} - "
          f"consultas hoy: {r['requests']['current']}/{r['requests']['limit_day']}\n")

    ligas = consultar(clave, "/leagues", current="true")["response"]
    actuales = {}
    for item in ligas:
        lid = item["league"]["id"]
        if lid in COMPETICIONES:
            temp = next((s for s in item["seasons"] if s.get("current")), None)
            if temp:
                actuales[lid] = temp

    print(f"{'Competicion':30} {'Temp.':6} {'Partidos':9} {'Estado'}")
    print("-" * 75)
    faltantes = []
    for lid, nombre in COMPETICIONES.items():
        temp = actuales.get(lid)
        if not temp:
            print(f"{nombre:30} {'-':6} {'-':9} sin temporada actual en la API")
            faltantes.append(nombre)
            continue
        anio = temp["year"]
        data = consultar(clave, "/fixtures", league=lid, season=anio)
        if data.get("errors"):
            print(f"{nombre:30} {anio:<6} {'-':9} NO DISPONIBLE: {data['errors']}")
            faltantes.append(nombre)
            continue
        cov = temp.get("coverage", {}).get("fixtures", {})
        extras = [k for k, v in {
            "stats": cov.get("statistics_fixtures"),
            "jugadores": cov.get("statistics_players"),
            "alineaciones": cov.get("lineups"),
            "lesiones": temp.get("coverage", {}).get("injuries"),
            "cuotas": temp.get("coverage", {}).get("odds"),
        }.items() if v]
        print(f"{nombre:30} {anio:<6} {data['results']:<9} OK ({', '.join(extras) or 'sin cobertura extra'})")

    print()
    if faltantes:
        print("ATENCION - no disponibles en tu plan:", ", ".join(faltantes))
    else:
        print("Las 6 competiciones estan disponibles.")


if __name__ == "__main__":
    main()
