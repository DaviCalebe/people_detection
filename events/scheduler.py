from datetime import datetime, timedelta
import time
import requests
from config.config import HEADERS
from guids.station_guids import STATION_PEOPLE_DETECTION_EVENT, STATION_BASE_URL, get_station_source, STATION_SOURCE_FULLTIME
import threading


def delay_deleting_event(formatted_time, delay_seconds=10):
    def delete():
        time.sleep(delay_seconds)
        delete_event_url = (
            f"{STATION_BASE_URL}/custom-events/"
            f"{STATION_PEOPLE_DETECTION_EVENT}/scheduled-times/{formatted_time}"
        )
        delete_response = requests.delete(
            delete_event_url, headers=HEADERS, verify=False
        )

        if delete_response.status_code == 204:
            print(f"Evento com horário {formatted_time} deletado com sucesso!")
        else:
            print(f"Erro ao deletar evento: {delete_response.status_code} - {delete_response.text}")

    threading.Thread(target=delete, daemon=True).start()


def set_event_schedule(camera_id, recorder_guid):
    STATION_SOURCE = get_station_source()
    now = datetime.now()
    scheduled_time = now + timedelta(seconds=10)
    formatted_time = scheduled_time.strftime("%H:%M:%S")

    # 1. Agendar evento
    add_event_url = (
        f"{STATION_BASE_URL}/custom-events/"
        f"{STATION_PEOPLE_DETECTION_EVENT}/scheduled-times"
    )

    data = {"scheduledTime": formatted_time}
    response = requests.post(add_event_url, headers=HEADERS, json=data, verify=False)

    if response.status_code in (200, 201):
        print("Evento agendado com sucesso! Time sent:", data)
    else:
        print(f"Erro ao agendar evento: {response.status_code} - {response.text} Time sent:", data)
        return response, None

    # 2. Ação fullscreen
    update_camera_url = f"{STATION_BASE_URL}/event-actions/sources/{STATION_SOURCE}/actions/fullscreen-camera"
    # update_camera_url = f"{STATION_BASE_URL}/event-actions/sources/{STATION_SOURCE_FULLTIME}/actions/fullscreen-camera"

    data = {
        "enabled": True,
        "serverGuid": recorder_guid,
        "cameraId": camera_id,
        "monitorId": 9,
        "shouldForceMonitor": True,
        "showLegend": True,
        "legendText": "$customevent.name$: $server.guid$",
        "legendPosition": 0,
        "legendFontCode": 0,
        "legendFontSize": 0,
        "legendFontColor": "FFFFFF",
        "legendShadowColor": "FF0000"
    }

    response = requests.put(update_camera_url, headers=HEADERS, json=data, verify=False)

    if response.status_code in (200, 201):
        print("Ação de câmera em tela cheia agendada com sucesso!")
    else:
        print(f"Erro ao agendar ação de câmera em tela cheia: {response.status_code} - {response.text}")

    # 3. Deletar evento depois, sem travar
    delay_deleting_event(formatted_time, delay_seconds=20)

    return response, None
