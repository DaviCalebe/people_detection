import requests
from config.config import HEADERS
from guids.station_guids import STATION_PEOPLE_DETECTION_EVENT, STATION_BASE_URL

def delete_all_scheduled_times():
    # 1. Endpoint que lista os horários
    list_url = f"{STATION_BASE_URL}/custom-events/{STATION_PEOPLE_DETECTION_EVENT}/scheduled-times"

    # 2. Pegar todos os horários já agendados
    response = requests.get(list_url, headers=HEADERS, verify=False)
    if response.status_code != 200:
        print(f"Erro ao buscar horários: {response.status_code} - {response.text}")
        return

    data = response.json()
    scheduled_times = data.get("scheduledTimes", [])

    if not scheduled_times:
        print("Nenhum horário encontrado para deletar.")
        return

    print(f"Foram encontrados {len(scheduled_times)} horários. Iniciando deleção...")

    # 3. Deletar cada horário
    for item in scheduled_times:
        formatted_time = item.get("scheduledTime")
        if not formatted_time:
            continue

        delete_url = (
            f"{STATION_BASE_URL}/custom-events/"
            f"{STATION_PEOPLE_DETECTION_EVENT}/scheduled-times/{formatted_time}"
        )

        del_response = requests.delete(delete_url, headers=HEADERS, verify=False)

        if del_response.status_code == 204:
            print(f"✅ Horário {formatted_time} deletado com sucesso.")
        else:
            print(f"❌ Erro ao deletar {formatted_time}: {del_response.status_code} - {del_response.text}")


# Exemplo de uso
if __name__ == "__main__":
    delete_all_scheduled_times()
