import requests

login_url = "https://10.10.50.181:7101/api/login"

credentials = {
    "username": "TesteAPI",
    "password": "Teste.1"
}

res = requests.post(login_url, json=credentials, verify=False)
token = res.json()['login']['userToken']
