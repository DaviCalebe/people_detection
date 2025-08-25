from helpers.apiHelper import post
from guids.server2_guids import SERVER2_BASE_URL

login_url = f"{SERVER2_BASE_URL}/login"

credentials = {
    "username": "TesteAPI",
    "password": "Teste.1"
}

res = post(login_url, json=credentials)
token = res.json()['login']['userToken']

HEADERS = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}
