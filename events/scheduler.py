from datetime import datetime, timedelta
import time
import requests
from config.config import HEADERS
from guids.station_guids import STATION_PEOPLE_DETECTION_EVENT, STATION_BASE_URL, STATION_SOURCE


def set_event_schedule():
    now = datetime.now()
    scheduled_time = now + timedelta(seconds=10)
    formatted_time = scheduled_time.strftime("%H:%M:%S")

    url = (
        f"{STATION_BASE_URL}/custom-events/"
        f"{STATION_PEOPLE_DETECTION_EVENT}/scheduled-times"
    )

    data = {
        "scheduledTime": formatted_time
    }

    response = requests.post(
        url, headers=HEADERS, json=data, verify=False
    )

    if response.status_code in (200, 201):
        print("Evento agendado com sucesso! Time sent:", data)
    else:
        print(f"Erro ao agendar evento: {response.status_code} - {response.text} Time sent:", data)

    time.sleep(1)

    delete_url = (
        f"{STATION_BASE_URL}/custom-events/"
        f"{STATION_PEOPLE_DETECTION_EVENT}/scheduled-times/{formatted_time}"
    )

    delete_response = requests.delete(
        delete_url, headers=HEADERS, verify=False
    )

    if delete_response.status_code == 204:
        print(f"Evento com horário {formatted_time} deletado com sucesso!")
    else:
        print(f"Erro ao deletar evento: {delete_response.status_code} - {delete_response.text}")

    return response, delete_response


def set_fullscreen_camera(camera_id, recorder_guid):
    url = f"{STATION_BASE_URL}/event-actions/sources/{STATION_SOURCE}/actions/fullscreen-camera"

    data = {
        "enabled": True,
        "serverGuid": recorder_guid,
        "cameraId": camera_id,
        "monitorId": 9,
        "shouldForceMonitor": True,
        "showLegend": True,
        "legendText": "$event.name$",
        "legendPosition": 0,
        "legendFontCode": 0,
        "legendFontSize": 0,
        "legendFontColor": "FFFFFF",
        "legendShadowColor": "FF0000"
    }

    print(camera_id, recorder_guid)

    response = requests.put(
        url, headers=HEADERS, json=data, verify=False)

    if response.status_code in (200, 201):
        print("Ação de câmera em tela cheia agendada com sucesso!")
    else:
        print(f"Erro ao agendar ação de câmera em tela cheia: {response.status_code} - {response.text}")