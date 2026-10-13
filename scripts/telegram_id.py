"""Muestra el ID de los canales donde el bot vio mensajes en las ultimas 24 hs.
Se corre desde GitHub Actions (usa el secreto del bot)."""
import json
import os
import urllib.request

token = os.environ["TELEGRAM_BOT_TOKEN"]


def api(metodo):
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{metodo}", timeout=30) as r:
        return json.load(r)


yo = api("getMe")["result"]
print(f"Bot OK: @{yo['username']} ({yo['first_name']})")
chats = {}
for u in api("getUpdates?allowed_updates=%5B%22channel_post%22%2C%22my_chat_member%22%5D")["result"]:
    for k in ("channel_post", "my_chat_member", "message"):
        if k in u:
            c = u[k]["chat"]
            chats[c["id"]] = f"{c.get('title') or c.get('username')} ({c['type']})"
if chats:
    for cid, nombre in chats.items():
        print(f"CANAL: {nombre} -> ID {cid}")
else:
    print("No se vio ningun mensaje. Publica algo en el canal y volve a correrlo.")
