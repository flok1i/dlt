"""Configuracion general de DLT."""
from datetime import timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CACHE = RAIZ / "cache"            # datos ya bajados (se guardan en el repo para no repetir)
SALIDA = RAIZ / "docs" / "data"   # JSON que lee la pagina

HORA_ARG = timezone(timedelta(hours=-3))  # Argentina no tiene horario de verano
DIAS_ADELANTE = 2                         # hoy + 2 dias
MIN_PARTIDOS = 5                          # menos que esto = "pocos datos"

# activa=False: todavia no se baja (se van sumando de a una)
COMPETICIONES = [
    {"id": "arg", "nombre": "Liga Profesional", "corto": "LPF", "espn": "arg.1", "fotmob": 112,
     "amarillas_suspension": 5, "activa": True},
    {"id": "bra", "nombre": "Brasileirão", "corto": "BRA", "espn": "bra.1", "fotmob": 268,
     "amarillas_suspension": 3, "activa": False},
    {"id": "ucl", "nombre": "Champions League", "corto": "UCL", "espn": "uefa.champions", "fotmob": 42,
     "amarillas_suspension": 3, "activa": False},
    {"id": "uel", "nombre": "Europa League", "corto": "UEL", "espn": "uefa.europa", "fotmob": 73,
     "amarillas_suspension": 3, "activa": False},
    {"id": "lib", "nombre": "Copa Libertadores", "corto": "LIB", "espn": "conmebol.libertadores", "fotmob": 45,
     "amarillas_suspension": 3, "activa": False},
    {"id": "sud", "nombre": "Copa Sudamericana", "corto": "SUD", "espn": "conmebol.sudamericana", "fotmob": 299,
     "amarillas_suspension": 3, "activa": False},
]

# Lineas de apuesta que se calculan
LINEAS = {
    "tarjetas": [2.5, 3.5, 4.5, 5.5, 6.5],
    "tarjetas_equipo": [0.5, 1.5, 2.5, 3.5],
    "corners": [7.5, 8.5, 9.5, 10.5, 11.5],
    "corners_equipo": [2.5, 3.5, 4.5, 5.5, 6.5],
    "faltas": [20.5, 22.5, 24.5, 26.5, 28.5],
    "faltas_equipo": [9.5, 10.5, 11.5, 12.5, 13.5],
}
