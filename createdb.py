import sqlite3
import json
import os

DB_NAME = "database.db"
JSON_NAME = "merged_inventory.json"  # seu arquivo JSON

# Remove o banco antigo se quiser recomeçar do zero (opcional)
if os.path.exists(DB_NAME):
    os.remove(DB_NAME)

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

cursor.executescript("""
CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS recorders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    guid TEXT,
    server_id INTEGER,
    FOREIGN KEY (server_id) REFERENCES servers (id)
);

CREATE TABLE IF NOT EXISTS cameras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    camera_id INTEGER,
    recorder_id INTEGER,
    FOREIGN KEY (recorder_id) REFERENCES recorders (id)
);

CREATE TABLE IF NOT EXISTS streams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stream_id INTEGER,
    url TEXT,
    username TEXT,
    password TEXT,
    camera_id INTEGER,
    FOREIGN KEY (camera_id) REFERENCES cameras (id)
);
""")

with open(JSON_NAME, 'r', encoding='utf-8') as f:
    data = json.load(f)

for server_name, server_info in data.get("servers", {}).items():
    cursor.execute("INSERT INTO servers (name) VALUES (?)", (server_name,))
    server_id = cursor.lastrowid

    for recorder_name, recorder_info in server_info.get("recorders", {}).items():
        guid = recorder_info.get("guid")
        cursor.execute(
            "INSERT INTO recorders (name, guid, server_id) VALUES (?, ?, ?)",
            (recorder_name, guid, server_id)
        )
        recorder_id = cursor.lastrowid

        for camera_name, camera_info in recorder_info.get("cameras", {}).items():
            camera_id_json = camera_info.get("id")
            cursor.execute(
                "INSERT INTO cameras (name, camera_id, recorder_id) VALUES (?, ?, ?)",
                (camera_name, camera_id_json, recorder_id)
            )
            camera_id = cursor.lastrowid

            for stream in camera_info.get("streams", []):
                stream_id = stream.get("streamId")
                remote = stream.get("remoteUrl", {})
                cursor.execute(
                    "INSERT INTO streams (stream_id, url, username, password, camera_id) VALUES (?, ?, ?, ?, ?)",
                    (
                        stream_id,
                        remote.get("url"),
                        remote.get("username"),
                        remote.get("password"),
                        camera_id
                    )
                )

conn.commit()
conn.close()

print("[OK] Banco de dados criado com sucesso a partir do merged_inventory.json!")
