"""Publica en el canal de Telegram las bajas nuevas y las alineaciones confirmadas.
Recuerda lo ya enviado en cache/avisos.json para no repetir.

Necesita las variables TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID (en GitHub van como secretos).
Sin ellas solo muestra en pantalla lo que mandaria.
"""
import html
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from actualizar import fecha_utc, guardar, leer, normalizar
from config import CACHE, HORA_ARG, PAGINA, SALIDA

ESTADO = CACHE / "avisos.json"
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT = os.environ.get("TELEGRAM_CHAT_ID")


def enviar(texto):
    if not TOKEN or not CHAT:
        print("--- (sin Telegram configurado, no se envía) ---\n" + texto + "\n")
        return True
    datos = urllib.parse.urlencode({"chat_id": CHAT, "text": texto, "parse_mode": "HTML",
                                    "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{TOKEN}/sendMessage", datos, timeout=30) as r:
            ok = json.load(r).get("ok", False)
    except Exception as err:
        print(f"! Telegram: {err}")
        ok = False
    time.sleep(1.5)  # Telegram limita los mensajes por minuto en canales
    return ok


def cuando(iso):
    f = fecha_utc(iso).astimezone(HORA_ARG)
    return f"{DIAS[f.weekday()]} {f:%d/%m %H:%M}"


def e(txt):
    return html.escape(str(txt or ""))


def frase_baja(b, rival):
    tipo = b["tipo"] or "Baja"
    t = tipo.lower()
    if t.startswith("posible"):
        return f"{tipo.lower()}, puede no jugar contra {rival}"
    if t.startswith("duda"):
        return f"en duda contra {rival}"
    return f"{t}, no juega contra {rival}"


def clave_baja(pid, b):
    return f"baja|{pid}|{normalizar(b['nombre'] or '')}"


def main():
    estado = leer(ESTADO, {}) or {}
    enviados = set(estado.get("enviados", []))
    vistos = set(estado.get("partidos", []))
    ahora = datetime.now(HORA_ARG)

    for archivo in sorted((SALIDA / "partido").glob("*.json")):
        d = leer(archivo)
        if not d or fecha_utc(d["fecha"]) < ahora - timedelta(hours=2):
            continue
        pid = d["id"]
        loc, vis = d["local"]["nombre"], d["visita"]["nombre"]
        link = f'<a href="{PAGINA}#/p/{pid}">Ver en DLT</a>'
        titulo = f"<b>{e(loc)} vs {e(vis)}</b> · {cuando(d['fecha'])}"
        bajas = [(k, b) for k in ("local", "visita") for b in d["bajas"][k]["bajas"]]

        inicio = fecha_utc(d["fecha"])
        if pid not in vistos:
            if inicio > ahora + timedelta(hours=24):
                continue  # el resumen se manda recien el dia anterior, asi no llegan todos juntos
            # primera vez que se avisa del partido: un solo mensaje con todas sus bajas
            if bajas and inicio > ahora:
                lineas = [f"🚑 <b>Bajas</b> · {titulo}"]
                for k, eq in (("local", loc), ("visita", vis)):
                    lista = d["bajas"][k]["bajas"]
                    if lista:
                        lineas.append(f"\n<b>{e(eq)}</b>")
                        lineas += [f"• {e(b['nombre'])} — {e(b['tipo'])}" for b in lista]
                lineas.append(f"\n{link}")
                if not enviar("\n".join(lineas)):
                    continue
            enviados.update(clave_baja(pid, b) for _, b in bajas)
            vistos.add(pid)
        else:
            for k, b in bajas:
                c = clave_baja(pid, b)
                if c in enviados:
                    continue
                equipo, rival = (loc, vis) if k == "local" else (vis, loc)
                texto = (f"🚑 <b>{e(b['nombre'])}</b> ({e(equipo)}): {e(frase_baja(b, rival))}.\n"
                         f"{titulo}\n{link}")
                if enviar(texto):
                    enviados.add(c)

        c = f"xi|{pid}"
        if d.get("alineacion_confirmada") and c not in enviados:
            al = d.get("alineaciones") or {}
            fm = d.get("formaciones") or {}
            partes = [f"📋 <b>Alineaciones confirmadas</b>\n{titulo}"]
            for k, eq in (("local", loc), ("visita", vis)):
                partes.append(f"\n<b>{e(eq)}</b>{f' ({e(fm.get(k))})' if fm.get(k) else ''}\n"
                              + ", ".join(e(n) for n in al.get(k, [])))
            partes.append(f"\n{link}")
            if enviar("\n".join(partes)):
                enviados.add(c)

    avisos_nba(enviados, vistos, ahora)

    if TOKEN and CHAT:  # en una prueba sin Telegram no se marca nada como enviado
        guardar(ESTADO, {"enviados": sorted(enviados), "partidos": sorted(vistos)})


ICONO_NBA = {"Descartado": "❌", "Dudoso": "⚠️", "Descansa": "💤"}
FRASE_NBA = {"Descartado": "descartado", "Dudoso": "pasa a dudoso", "Descansa": "descansa, no juega"}


def avisos_nba(enviados, vistos, ahora):
    """NBA: resumen del parte de lesiones el dia del partido y despues cada cambio (descartado / dudoso)."""
    for archivo in sorted((SALIDA / "nba" / "partido").glob("*.json")):
        d = leer(archivo)
        if not d or fecha_utc(d["fecha"]) < ahora - timedelta(hours=1):
            continue
        pid = f"nba-{d['id']}"
        loc, vis = d["local"]["nombre"], d["visita"]["nombre"]
        inicio = fecha_utc(d["fecha"])
        link = f'<a href="{PAGINA}#/nba/p/{d["id"]}">Ver en DLT</a>'
        titulo = f"🏀 <b>{e(vis)} @ {e(loc)}</b> · {cuando(d['fecha'])}"
        bajas = [(k, b) for k in ("visita", "local") for b in d["bajas"][k]]
        clave = lambda b: f"nbabaja|{pid}|{b['id'] or normalizar(b['nombre'] or '')}|{b['estado']}"
        if pid not in vistos:
            if inicio > ahora + timedelta(hours=24):
                continue
            if bajas and inicio > ahora:
                lineas = [f"{titulo}\n<b>Parte de lesiones</b>"]
                for k, eq in (("visita", vis), ("local", loc)):
                    if d["bajas"][k]:
                        lineas.append(f"\n<b>{e(eq)}</b>")
                        lineas += [f"{ICONO_NBA.get(b['estado'], '•')} {e(b['nombre'])} — {e(b['estado'].lower())}"
                                   + (f" ({e(b['motivo'])})" if b.get("motivo") else "") for b in d["bajas"][k]]
                lineas.append(f"\n{link}")
                if not enviar("\n".join(lineas)):
                    continue
            enviados.update(clave(b) for _, b in bajas)
            vistos.add(pid)
            continue
        for k, b in bajas:
            c = clave(b)
            if c in enviados:
                continue
            equipo, rival = (loc, vis) if k == "local" else (vis, loc)
            texto = (f"{ICONO_NBA.get(b['estado'], '•')} <b>{e(b['nombre'])}</b> ({e(equipo)}) "
                     f"{FRASE_NBA.get(b['estado'], b['estado'].lower())} contra {e(rival)}"
                     + (f" — {e(b['motivo'])}" if b.get("motivo") else "") + f".\n{titulo}\n{link}")
            if enviar(texto):
                enviados.add(c)


if __name__ == "__main__":
    main()
