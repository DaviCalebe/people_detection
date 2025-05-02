import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get(url, **kwargs):
    kwargs.setdefault("verify", False)
    try:
        response = requests.get(url, **kwargs)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as err:
        print(f"[GET Error] {err} - URL: {url}")
        return None


def post(url, **kwargs):
    kwargs.setdefault("verify", False)
    try:
        response = requests.post(url, **kwargs)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as err:
        print(f"[POST Error] {err} - URL: {url}")
    return None


def put(url, **kwargs):
    kwargs.setdefault("verify", False)
    try:
        response = requests.put(url, **kwargs)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as err:
        print(f"[PUT Error] {err} - URL: {url}")
    return None


def delete(url, **kwargs):
    kwargs.setdefault("verify", False)
    try:
        response = requests.delete(url, **kwargs)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as err:
        print(f"[DELETE Error] {err} - URL: {url}")
    return None
