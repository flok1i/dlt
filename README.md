# DLT

Estadísticas de fútbol para analizar apuestas: tarjetas, córners, faltas, jugadores, bajas e historial,
con probabilidades (Poisson) y comparador de cuotas bet365 / Betano.

- `scripts/actualizar.py`: baja datos de ESPN y FotMob, calcula y genera `docs/data/*.json`.
- `docs/`: la página (GitHub Pages).
- `cache/`: partidos ya bajados, para no repetir consultas.
- `.github/workflows/actualizar.yml`: actualización automática.

Correr a mano: `python scripts/actualizar.py`
