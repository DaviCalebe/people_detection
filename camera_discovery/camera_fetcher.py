from config.config import HEADERS
from helpers.apiHelper import get
from scripts.server1_guids import SERVER1_BASE_URL
import json
from datetime import datetime
import os


def export_to_json(data, filename_prefix="servers_data"):
    """Exporta os dados em formato JSON com timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.json"

    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"\n✅ Arquivo exportado com sucesso: {os.path.abspath(filename)}")
    except Exception as e:
        print(f"\n❌ Erro ao exportar o JSON: {str(e)}")


def get_servers():
    print("Fetching servers...")
    url = f"{SERVER1_BASE_URL}/servers"
    response = get(url, headers=HEADERS)
    if not response:
        return []

    data = response.json()
    servers = data.get("servers", [])
    server_list = []
    for server in servers:
        name = server.get("name")
        guid = server.get("guid")
        server_list.append({"name": name, "guid": guid})

    print(f"Found {len(server_list)} servers.")
    for server in server_list:
        print(f"Server: {server['name']}, GUID: {server['guid']}")
    return server_list


def get_cameras_by_server(server_guid):
    url = f"{SERVER1_BASE_URL}/servers/{server_guid}/cameras"
    response = get(url, headers=HEADERS)
    if not response:
        return []

    data = response.json()
    cameras = data.get("cameras", [])
    camera_list = []
    for camera in cameras:
        name = camera.get("name")
        camera_id = camera.get("id")
        camera_list.append({"name": name, "id": camera_id})
    print(f"Found {len(camera_list)} cameras for server {server_guid}.")
    for camera in camera_list:
        print(f"Camera: {camera['name']}, ID: {camera['id']}")
    return camera_list


def get_stream_ids(server_guid, camera_id):
    url = (
        f"{SERVER1_BASE_URL}/servers/{server_guid}/cameras/"
        f"{camera_id}/streams"
    )
    response = get(url, headers=HEADERS)
    if not response:
        print("Erro: sem resposta da API.")
        return None

    data = response.json()
    streams = data.get("streams", [])

    if not streams:
        print("Nenhum stream encontrado.")
        return None

    # Extrai os IDs dos streams
    stream_ids = [stream.get("id") for stream in streams if "id" in stream]

    print(f"IDs encontrados: {stream_ids}")
    return stream_ids


def get_remote_url(server_guid, camera_id, stream_id=0):
    url = (
        f"{SERVER1_BASE_URL}/servers/{server_guid}/cameras/"
        f"{camera_id}/streams/{stream_id}/remote-url"
    )
    response = get(url, headers=HEADERS)
    if not response:
        return {}

    data = response.json()
    remote = data.get("remoteUrl", {})

    result = {
        "url": remote.get("url"),
        "username": remote.get("username"),
        "password": remote.get("password"),
    }

    print(f"Dados para stream_id {stream_id}: {result}")
    return result


def build_full_server_list():
    full_data = []

    servers = get_servers()
    if not servers:
        print("Nenhum servidor encontrado.")
        return full_data

    for server in servers:
        server_entry = {
            "name": server.get("name", "Indisponível"),
            "guid": server.get("guid", "Indisponível"),
            "cameras": []
        }

        try:
            cameras = get_cameras_by_server(server["guid"])
        except Exception as e:
            print(f"Erro ao buscar câmeras do servidor {server['guid']}: {e}")
            server_entry["cameras"].append({
                "name": "Indisponível",
                "id": "Indisponível",
                "streams": []
            })
            full_data.append(server_entry)
            continue

        if not cameras:
            server_entry["cameras"].append({
                "name": "Indisponível",
                "id": "Indisponível",
                "streams": []
            })
            full_data.append(server_entry)
            continue

        for camera in cameras:
            camera_entry = {
                "name": camera.get("name", "Indisponível"),
                "id": camera.get("id", "Indisponível"),
                "streams": []
            }

            try:
                stream_ids = get_stream_ids(server["guid"], camera["id"])
            except Exception as e:
                print(f"Erro ao buscar streams da câmera {camera['id']}: {e}")
                camera_entry["streams"].append({
                    "streamId": "Indisponível",
                    "remoteUrl": {
                        "url": "Indisponível",
                        "username": "Indisponível",
                        "password": "Indisponível"
                    }
                })
                server_entry["cameras"].append(camera_entry)
                continue

            if not stream_ids:
                camera_entry["streams"].append({
                    "streamId": "Indisponível",
                    "remoteUrl": {
                        "url": "Indisponível",
                        "username": "Indisponível",
                        "password": "Indisponível"
                    }
                })
                server_entry["cameras"].append(camera_entry)
                continue

            for stream_id in stream_ids:
                try:
                    remote = get_remote_url(server["guid"], camera["id"], stream_id)
                except Exception as e:
                    print(f"Erro ao buscar remoteUrl do stream {stream_id}: {e}")
                    remote = {
                        "url": "Indisponível",
                        "username": "Indisponível",
                        "password": "Indisponível"
                    }

                if not remote or not remote.get("url"):
                    remote = {
                        "url": "Indisponível",
                        "username": "Indisponível",
                        "password": "Indisponível"
                    }

                camera_entry["streams"].append({
                    "streamId": stream_id,
                    "remoteUrl": remote
                })

            server_entry["cameras"].append(camera_entry)

        full_data.append(server_entry)

    print("Estrutura completa montada com sucesso.")
    return full_data


if __name__ == "__main__":
    data = build_full_server_list()
    export_to_json(data)
