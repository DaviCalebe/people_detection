from datetime import datetime, timedelta
import time
import requests
from config.config import HEADERS
from scripts.station_guids import STATION_PEOPLE_DETECTION_EVENT, STATION_BASE_URL


def set_event_schedule():
    now = datetime.now()
    scheduled_time = now - timedelta(minutes=1)
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
