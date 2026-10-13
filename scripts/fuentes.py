"""Descarga de datos de ESPN y FotMob (sitios publicos, sin clave)."""
import json
import time
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"
FOTMOB = "https://www.fotmob.com/api/data"

contador = {"espn": 0, "fotmob": 0}


def bajar(url, fuente, intentos=3):
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                contador[fuente] += 1
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code in (400, 403, 404):
                raise
            if i == intentos - 1:
                raise
            time.sleep(2 * (i + 1))


def espn_dia(liga, fecha):
    """Partidos de una liga en un dia (fecha = date)."""
    return bajar(f"{ESPN}/{liga}/scoreboard?dates={fecha:%Y%m%d}", "espn")


def espn_partido(liga, evento_id):
    return bajar(f"{ESPN}/{liga}/summary?event={evento_id}", "espn")


def espn_equipo(equipo_id, temporada=None):
    """Partidos de un equipo en TODAS sus competiciones (liga local, copas, amistosos)."""
    extra = f"?season={temporada}" if temporada else ""
    return bajar(f"{ESPN}/all/teams/{equipo_id}/schedule{extra}", "espn")


def fotmob_dia(fecha):
    return bajar(f"{FOTMOB}/matches?date={fecha:%Y%m%d}", "fotmob")


def fotmob_partido(match_id):
    return bajar(f"{FOTMOB}/matchDetails?matchId={match_id}", "fotmob")
