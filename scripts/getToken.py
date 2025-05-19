from helpers.apiHelper import post

login_url = "http://10.10.50.180:7102/api/login"

credentials = {
    "username": "TesteAPI",
    "password": "Teste.1"
}

res = post(login_url, json=credentials)
token = res.json()['login']['userToken']
print(token)
