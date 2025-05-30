import sqlite3
import json

DB_NAME = "database.db"
JSON_NAME = "merged_inventory.json"

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

with open(JSON_NAME, 'r', encoding='utf-8') as f:
    data = json.load(f)

updates = 0
updated_streams = []

for server_info in data.get("servers", {}).values():
    for recorder_info in server_info.get("recorders", {}).values():
        for camera_info in recorder_info.get("cameras", {}).values():
            camera_id_json = camera_info.get("id")

            for stream in camera_info.get("streams", []):
                stream_id = stream.get("streamId")
                remote = stream.get("remoteUrl", {})

                if not remote.get("url"):
                    continue

                cursor.execute("""
                    SELECT id FROM streams
                    WHERE stream_id = ? AND camera_id = ? AND (url IS NULL OR url = '')
                """, (stream_id, camera_id_json))
                result = cursor.fetchone()

                if result:
                    cursor.execute("""
                        UPDATE streams
                        SET url = ?, username = ?, password = ?
                        WHERE stream_id = ? AND camera_id = ?
                    """, (
                        remote.get("url"),
                        remote.get("username"),
                        remote.get("password"),
                        stream_id,
                        camera_id_json
                    ))
                    updates += 1
                    updated_streams.append({
                        "camera_id": camera_id_json,
                        "stream_id": stream_id,
                        "url": remote.get("url"),
                        "username": remote.get("username"),
                        "password": remote.get("password")
                    })

conn.commit()
conn.close()

print(f"[OK] {updates} stream(s) com URL atualizada(s):\n")

# Exibe as atualizações
for s in updated_streams:
    print(f"camera_id: {s['camera_id']}, stream_id: {s['stream_id']}, url: {s['url']}")
