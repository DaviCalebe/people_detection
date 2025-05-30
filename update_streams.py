import json
import os
from datetime import datetime
from config.config import HEADERS
from helpers.apiHelper import get
from scripts.server1_guids import SERVER1_BASE_URL

JSON_PATH = "merged_inventory.json"
TEMP_PATH = "merged_inventory_temp.json"
BACKUP_SUFFIX = datetime.now().strftime("%Y%m%d_%H%M%S")

def get_remote_url(recorder_guid, camera_id, stream_id, recorder_name, camera_name):
    url = f"{SERVER1_BASE_URL}/servers/{recorder_guid}/cameras/{camera_id}/streams/{stream_id}/remote-url"
    response = get(url, headers=HEADERS)

    if not response:
        print(f"[ERRO] Falha ao buscar remoteUrl para stream '{stream_id}' da câmera '{camera_name}' no recorder '{recorder_name}'")
        return None

    try:
        response.raise_for_status()
        data = response.json()
        remote_data = data.get("remoteUrl", {})
        return {
            "url": remote_data.get("url"),
            "username": remote_data.get("username"),
            "password": remote_data.get("password"),
        }
    except Exception as e:
        print(f"[ERRO] Exceção ao processar resposta do remoteUrl para stream '{stream_id}': {e}")
        return None


def save_temp_json(data):
    with open(TEMP_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def update_remote_urls(json_path):
    # Carregar JSON principal ou temporário, se existir
    if os.path.exists(TEMP_PATH):
        print(f"[INFO] Retomando a partir de arquivo temporário: {TEMP_PATH}")
        with open(TEMP_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        print(f"[ERRO] Arquivo não encontrado: {json_path}")
        return

    # Percorrer estrutura
    for server_name, server_data in data.get("servers", {}).items():
        for recorder_name, recorder_data in server_data.get("recorders", {}).items():
            recorder_guid = recorder_data.get("guid")
            for camera_name, camera_data in recorder_data.get("cameras", {}).items():
                camera_id = camera_data.get("id")
                for stream in camera_data.get("streams", []):
                    stream_id = stream.get("streamId")

                    # Pular se streamId inválido
                    if stream_id == "Indisponível":
                        continue

                    # Pular se remoteUrl já estiver completo
                    existing = stream.get("remoteUrl", {})
                    if all(existing.get(k) not in [None, ""] for k in ["url", "username", "password"]):
                        continue

                    try:
                        remote_url = get_remote_url(
                            recorder_guid,
                            camera_id,
                            stream_id,
                            recorder_name,
                            camera_name
                        )
                        if remote_url:
                            stream["remoteUrl"] = remote_url
                            print(f"[OK] Atualizado: {server_name} > {recorder_name} > {camera_name} > Stream {stream_id}")
                            save_temp_json(data)
                        else:
                            print(f"[AVISO] remoteUrl não disponível para stream {stream_id} da câmera {camera_name}")

                    except Exception as e:
                        print(f"[ERRO] Exceção ao atualizar stream {stream_id} da câmera {camera_name}: {e}")

    # Criar backup
    base, ext = os.path.splitext(json_path)
    backup_path = f"{base}_backup_{BACKUP_SUFFIX}{ext}"
    os.rename(json_path, backup_path)
    print(f"[INFO] Backup salvo: {backup_path}")

    # Salvar JSON final
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"[INFO] JSON final salvo em: {json_path}")

    # Remover arquivo temporário
    if os.path.exists(TEMP_PATH):
        os.remove(TEMP_PATH)
        print(f"[INFO] Arquivo temporário removido: {TEMP_PATH}")


if __name__ == "__main__":
    update_remote_urls(JSON_PATH)
