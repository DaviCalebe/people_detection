import sqlite3
import json

DB_NAME = "database.db"
JSON_NAME = "merged_inventory.json"

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# Carrega JSON
with open(JSON_NAME, 'r', encoding='utf-8') as f:
    data = json.load(f)

updates = 0
updated_streams = []

# Buscar todas as streams com algum campo NULL ou vazio
cursor.execute("""
    SELECT s.id, s.stream_id, s.url, s.username, s.password, s.camera_id,
           c.camera_id AS json_camera_id, r.name AS recorder_name, rec.server_id,
           srv.name AS server_name
    FROM streams s
    JOIN cameras c ON s.camera_id = c.id
    JOIN recorders r ON c.recorder_id = r.id
    JOIN servers srv ON r.server_id = srv.id
""")
all_streams = cursor.fetchall()

for (stream_db_id, stream_id, url_db, username_db, password_db,
     camera_db_id, json_camera_id, recorder_name, server_id, server_name) in all_streams:

    # Verifica se algum campo está vazio ou NULL
    if (url_db not in (None, '', 'NULL')) and (username_db not in (None, '', 'NULL')) and (password_db not in (None, '', 'NULL')):
        continue  # já preenchido tudo, pula

    # Acessar o JSON para buscar o valor correto
    server_json = data.get("servers", {}).get(server_name)
    if not server_json:
        continue
    recorder_json = server_json.get("recorders", {}).get(recorder_name)
    if not recorder_json:
        continue
    cameras_json = recorder_json.get("cameras", {})

    # Acha a câmera no JSON pelo camera_id
    camera_json = None
    for cam_name, cam_info in cameras_json.items():
        if cam_info.get("id") == json_camera_id:
            camera_json = cam_info
            break
    if not camera_json:
        continue

    # Acha o stream no JSON com o stream_id correto
    stream_json = None
    for st in camera_json.get("streams", []):
        if st.get("streamId") == stream_id:
            stream_json = st
            break
    if not stream_json:
        continue

    remote = stream_json.get("remoteUrl", {})

    # Se o campo no banco está vazio/nulo e no JSON tem valor, atualiza
    new_url = url_db
    new_username = username_db
    new_password = password_db

    if (url_db in (None, '', 'NULL')) and remote.get("url"):
        new_url = remote.get("url")
    if (username_db in (None, '', 'NULL')) and remote.get("username"):
        new_username = remote.get("username")
    if (password_db in (None, '', 'NULL')) and remote.get("password"):
        new_password = remote.get("password")

    # Só atualiza se pelo menos um campo mudou
    if (new_url != url_db) or (new_username != username_db) or (new_password != password_db):
        cursor.execute("""
            UPDATE streams
            SET url = ?, username = ?, password = ?
            WHERE id = ?
        """, (new_url, new_username, new_password, stream_db_id))
        updates += 1
        updated_streams.append({
            "server": server_name,
            "recorder": recorder_name,
            "camera_id": json_camera_id,
            "stream_id": stream_id,
            "url": new_url,
            "username": new_username,
            "password": new_password,
        })

conn.commit()
conn.close()

print(f"[OK] {updates} stream(s) atualizada(s) com dados do JSON.\n")
for s in updated_streams:
    print(f"Server: {s['server']}, Recorder: {s['recorder']}, Camera ID: {s['camera_id']}, Stream ID: {s['stream_id']}, URL: {s['url']}")
