import sqlite3
import json
import os

def create_tables(cursor):
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

def insert_data_from_json(json_file, db_file):
    if not os.path.exists(json_file):
        print(f"❌ Arquivo '{json_file}' não encontrado.")
        return

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    create_tables(cursor)

    for server_name, recorders in data["servers"].items():
        # Insere o servidor
        cursor.execute("INSERT OR IGNORE INTO servers (name) VALUES (?)", (server_name,))
        cursor.execute("SELECT id FROM servers WHERE name = ?", (server_name,))
        server_id = cursor.fetchone()[0]

        for recorder_name, recorder_data in recorders.items():
            guid = recorder_data.get("guid", "")
            cursor.execute("""
                INSERT INTO recorders (name, guid, server_id)
                VALUES (?, ?, ?)""", (recorder_name, guid, server_id))
            recorder_id = cursor.lastrowid

            for cam in recorder_data.get("cameras", []):
                cam_name = cam.get("name", "")
                cam_id = cam.get("id", 0)
                cursor.execute("""
                    INSERT INTO cameras (name, camera_id, recorder_id)
                    VALUES (?, ?, ?)""", (cam_name, cam_id, recorder_id))
                camera_id = cursor.lastrowid

                for stream in cam.get("streams", []):
                    remote = stream.get("remoteUrl", {})
                    cursor.execute("""
                        INSERT INTO streams (stream_id, url, username, password, camera_id)
                        VALUES (?, ?, ?, ?, ?)""", (
                            stream.get("streamId"),
                            remote.get("url"),
                            remote.get("username"),
                            remote.get("password"),
                            camera_id
                        ))

    conn.commit()
    conn.close()
    print(f"[OK] Dados inseridos em '{db_file}' com sucesso.")

if __name__ == "__main__":
    insert_data_from_json("merged_inventory.json", "dguard.db")
