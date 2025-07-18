from config.config import HEADERS
from helpers.apiHelper import get
from guids.station_guids import STATION_BASE_URL
import json
from datetime import datetime
import os


IN_PROGRESS_FILE = "recorders_data_in_progress.json"


def export_to_json(data, filename_prefix="recorders_data"):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.json"

    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"\n✅ Arquivo exportado com sucesso: {os.path.abspath(filename)}")
    except Exception as e:
        print(f"\n❌ Erro ao exportar o JSON: {str(e)}")


def save_progress(data):
    with open(IN_PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"💾 Progresso salvo: {IN_PROGRESS_FILE}")


def load_progress():
    if os.path.exists(IN_PROGRESS_FILE):
        with open(IN_PROGRESS_FILE, "r", encoding="utf-8") as f:
            print(f"🔄 Retomando progresso de {IN_PROGRESS_FILE}")
            return json.load(f)
    return []


def get_recorders():
    print("Fetching recorders...")
    url = f"{STATION_BASE_URL}/servers"
    response = get(url, headers=HEADERS)
    if not response:
        return []

    data = response.json()
    recorders = data.get("servers", [])
    recorder_list = []
    for recorder in recorders:
        name = recorder.get("name")
        guid = recorder.get("guid")
        recorder_list.append({"name": name, "guid": guid})

    print(f"Found {len(recorder_list)} recorders.")
    return recorder_list


def get_cameras_by_recorder(recorder_guid, recorder_name):
    url = f"{STATION_BASE_URL}/servers/{recorder_guid}/cameras"
    response = get(url, headers=HEADERS)
    if not response:
        print(f"⚠️ Erro: sem resposta ao buscar câmeras do recorder {recorder_name} ({recorder_guid})")
        return []

    data = response.json()
    cameras = data.get("cameras", [])
    camera_list = []
    for camera in cameras:
        name = camera.get("name")
        camera_id = camera.get("id")
        camera_list.append({"name": name, "id": camera_id})
    print(f"Found {len(camera_list)} cameras for recorder {recorder_name}.")
    return camera_list


def get_stream_ids(recorder_guid, camera_id, recorder_name, camera_name):
    url = f"{STATION_BASE_URL}/servers/{recorder_guid}/cameras/{camera_id}/streams"
    response = get(url, headers=HEADERS)
    if not response:
        print(f"⚠️ Erro: sem resposta ao buscar streams da câmera {camera_name} ({camera_id}) no recorder {recorder_name}")
        return None

    data = response.json()
    streams = data.get("streams", [])
    if not streams:
        print(f"⚠️ Nenhum stream encontrado para câmera {camera_name} ({camera_id}) no recorder {recorder_name}")
        return None

    stream_ids = [stream.get("id") for stream in streams if "id" in stream]
    return stream_ids


def get_remote_url(recorder_guid, camera_id, stream_id, recorder_name, camera_name):
    url = f"{STATION_BASE_URL}/servers/{recorder_guid}/cameras/{camera_id}/streams/{stream_id}/remote-url"
    response = get(url, headers=HEADERS)
    if not response:
        print(f"⚠️ Erro ao buscar remoteUrl do stream {stream_id} da câmera {camera_name} no recorder {recorder_name}")
        return {}

    data = response.json()
    remote = data.get("remoteUrl", {})

    result = {
        "url": remote.get("url"),
        "username": remote.get("username"),
        "password": remote.get("password"),
    }

    return result


def build_full_recorder_list():
    progress_data = load_progress()
    processed_guids = {rec["guid"] for rec in progress_data}

    recorders = get_recorders()
    if not recorders:
        print("Nenhum recorder encontrado.")
        return progress_data

    for recorder in recorders:
        if recorder["guid"] in processed_guids:
            print(f"⏩ Recorder já processado: {recorder['name']}")
            continue

        recorder_entry = {
            "name": recorder.get("name", "Indisponível"),
            "guid": recorder.get("guid", "Indisponível"),
            "cameras": []
        }

        try:
            cameras = get_cameras_by_recorder(recorder["guid"], recorder["name"])
        except Exception as e:
            print(f"❌ Erro ao buscar câmeras do recorder {recorder['name']} ({recorder['guid']}): {e}")
            cameras = []

        if not cameras:
            recorder_entry["cameras"].append({
                "name": "Indisponível",
                "id": "Indisponível",
                "streams": []
            })
            progress_data.append(recorder_entry)
            save_progress(progress_data)
            continue

        for camera in cameras:
            camera_entry = {
                "name": camera.get("name", "Indisponível"),
                "id": camera.get("id", "Indisponível"),
                "streams": []
            }

            try:
                stream_ids = get_stream_ids(recorder["guid"], camera["id"], recorder["name"], camera["name"])
            except Exception as e:
                print(f"❌ Erro ao buscar streams da câmera {camera['name']} ({camera['id']}) no recorder {recorder['name']}: {e}")
                stream_ids = None

            if not stream_ids:
                camera_entry["streams"].append({
                    "streamId": "Indisponível",
                    "remoteUrl": {
                        "url": "Indisponível",
                        "username": "Indisponível",
                        "password": "Indisponível"
                    }
                })
                recorder_entry["cameras"].append(camera_entry)
                continue

            for stream_id in stream_ids:
                try:
                    remote = get_remote_url(recorder["guid"], camera["id"], stream_id, recorder["name"], camera["name"])
                except Exception as e:
                    print(f"❌ Erro ao buscar remoteUrl do stream {stream_id} da câmera {camera['name']} no recorder {recorder['name']}: {e}")
                    remote = {}

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

            recorder_entry["cameras"].append(camera_entry)

        progress_data.append(recorder_entry)
        save_progress(progress_data)

    print("Estrutura completa montada com sucesso.")
    return progress_data


""" if __name__ == "__main__":
    data = build_full_recorder_list()

    # Exportar resultado final
    export_to_json(data)

    # Limpar arquivo de progresso
    if os.path.exists(IN_PROGRESS_FILE):
        os.remove(IN_PROGRESS_FILE)
        print(f"🗑️ Progresso removido: {IN_PROGRESS_FILE}")
 """


def get_recorder_by_guid(guid):
    url = f"{STATION_BASE_URL}/servers"
    response = get(url, headers=HEADERS)
    if not response:
        return None

    data = response.json()
    for recorder in data.get("servers", []):
        if recorder.get("guid") == guid:
            return {
                "name": recorder.get("name", "Indisponível"),
                "guid": recorder.get("guid", "Indisponível")
            }

    return None


def build_single_recorder_entry(recorder_guid):
    recorder = get_recorder_by_guid(recorder_guid)
    if not recorder:
        print(f"❌ Recorder com GUID {recorder_guid} não encontrado.")
        return None

    recorder_entry = {
        "name": recorder["name"],
        "guid": recorder["guid"],
        "cameras": []
    }

    try:
        cameras = get_cameras_by_recorder(recorder["guid"], recorder["name"])
    except Exception as e:
        print(f"❌ Erro ao buscar câmeras do recorder {recorder['name']}: {e}")
        return recorder_entry

    for camera in cameras:
        camera_entry = {
            "name": camera.get("name", "Indisponível"),
            "id": camera.get("id", "Indisponível"),
            "streams": []
        }

        try:
            stream_ids = get_stream_ids(recorder["guid"], camera["id"], recorder["name"], camera["name"])
        except Exception as e:
            print(f"❌ Erro ao buscar streams da câmera {camera['name']}: {e}")
            stream_ids = []

        if not stream_ids:
            camera_entry["streams"].append({
                "streamId": "Indisponível",
                "remoteUrl": {
                    "url": "Indisponível",
                    "username": "Indisponível",
                    "password": "Indisponível"
                }
            })
        else:
            for stream_id in stream_ids:
                remote = get_remote_url(recorder["guid"], camera["id"], stream_id, recorder["name"], camera["name"]) or {}
                if not remote.get("url"):
                    remote = {
                        "url": "Indisponível",
                        "username": "Indisponível",
                        "password": "Indisponível"
                    }
                camera_entry["streams"].append({
                    "streamId": stream_id,
                    "remoteUrl": remote
                })

        recorder_entry["cameras"].append(camera_entry)

    return recorder_entry


if __name__ == "__main__":
    # Substitua pelo GUID do novo gravador
    new_recorder_guid = "{8CA2FED6-F6DF-43D5-9B85-82876BFE9024}"

    recorder_entry = build_single_recorder_entry(new_recorder_guid)
    if recorder_entry:
        export_to_json([recorder_entry], filename_prefix="new_recorder")

        # Opcional: você pode também salvar no progresso acumulado se quiser
        progress = load_progress()
        progress.append(recorder_entry)
        save_progress(progress)
