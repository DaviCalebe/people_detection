import json
import sqlite3

# Arquivo JSON com os gravadores que você quer importar
JSON_FILE = "selected_recorders_20250825_091237.json"

# Banco SQLite existente
DB_FILE = "database.db"

def update_server2():
    # Conecta no banco
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Lê o JSON
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Busca o id do server 2
    cursor.execute("SELECT id FROM servers WHERE name = ?", ("server2",))
    server_row = cursor.fetchone()
    if not server_row:
        print("❌ Server 'server2' não encontrado no banco!")
        conn.close()
        return
    server_id = server_row[0]

    for recorder in data:
        recorder_name = recorder["name"].replace(" ", "_").upper()
        recorder_guid = recorder["guid"]

        # Verifica se o recorder já existe
        cursor.execute("SELECT id FROM recorders WHERE guid = ?", (recorder_guid,))
        row = cursor.fetchone()
        if row:
            print(f"⚠️ GUID já existe para recorder '{recorder_name}', alterando para 'REVISAR'")
            recorder_guid_db = "REVISAR"
        else:
            recorder_guid_db = recorder_guid

        # Insere recorder
        cursor.execute("""
            INSERT INTO recorders (server_id, name, guid)
            VALUES (?, ?, ?)
        """, (server_id, recorder_name, recorder_guid_db))
        recorder_id = cursor.lastrowid

        for camera in recorder.get("cameras", []):
            camera_name = camera["name"].strip().replace(" ", "_").lower()
            dguard_camera_id = camera["id"]

            # Verifica se a camera já existe
            cursor.execute("""
                SELECT id FROM cameras 
                WHERE recorder_id = ? AND camera_id = ?
            """, (recorder_id, dguard_camera_id))
            cam_row = cursor.fetchone()
            if cam_row:
                camera_id = cam_row[0]
            else:
                cursor.execute("""
                    INSERT INTO cameras (recorder_id, name, camera_id)
                    VALUES (?, ?, ?)
                """, (recorder_id, camera_name, dguard_camera_id))
                camera_id = cursor.lastrowid

            for stream in camera.get("streams", []):
                stream_id = stream["streamId"]
                url = stream["remoteUrl"]["url"]
                username = stream["remoteUrl"].get("username")
                password = stream["remoteUrl"].get("password")

                # Verifica se o stream já existe
                cursor.execute("""
                    SELECT id FROM streams WHERE camera_id = ? AND stream_id = ?
                """, (camera_id, stream_id))
                stream_row = cursor.fetchone()
                if stream_row:
                    # Atualiza stream existente
                    cursor.execute("""
                        UPDATE streams SET url = ?, username = ?, password = ?
                        WHERE id = ?
                    """, (url, username, password, stream_row[0]))
                else:
                    # Insere novo stream
                    cursor.execute("""
                        INSERT INTO streams (camera_id, stream_id, url, username, password)
                        VALUES (?, ?, ?, ?, ?)
                    """, (camera_id, stream_id, url, username, password))

    # Salva mudanças e fecha conexão
    conn.commit()
    conn.close()
    print("✅ Importação concluída para server2")

if __name__ == "__main__":
    update_server2()