from config.config import SERVER1_BASE_URL, HEADERS
from helpers.apiHelper import get


def get_servers():
    print("Fetching servers...")
    url = f"{SERVER1_BASE_URL}/servers"
    response = get(url, headers=HEADERS)
    if not response:
        return []

    data = response.json()
    servers = data.get("servers", [])
    server_list = []
    for server in servers:
        name = server.get("name")
        guid = server.get("guid")
        server_list.append({"name": name, "guid": guid})

    print(f"Found {len(server_list)} servers.")
    for server in server_list:
        print(f"Server: {server['name']}, GUID: {server['guid']}")
    return server_list


get_servers()


def get_cameras_by_server(server_guid):
    url = f"{SERVER1_BASE_URL}/servers/{server_guid}/cameras"
    response = get(url, headers=HEADERS)
    if not response:
        return []

    data = response.json()
    cameras = data.get("cameras", [])
    camera_list = []
    for camera in cameras:
        name = camera.get("name")
        camera_id = camera.get("id")
        camera_list.append({"name": name, "id": camera_id})
    print(f"Found {len(camera_list)} cameras for server {server_guid}.")
    for camera in camera_list:
        print(f"Camera: {camera['name']}, ID: {camera['id']}")
    return camera_list


get_cameras_by_server("{64147D76-11DD-415D-AE4A-F4EA8159CB3A}")


""" def get_stream_id(server_guid, camera_id, stream_id=0):
    url = (
        f"{SERVER1_BASE_URL}/servers/{server_guid}/cameras/"
        f"{camera_id}/streams/{stream_id}"
    )
    response = get(url, headers=HEADERS)
    if not response:
        return None

    stream = response.json()
    return stream.get("id")

get_stream_id("{771ED3D0-9BA1-4B2A-B3D4-82A78B5B7E19}", "1", 0) """


""" def get_remote_url(server_guid, camera_id, stream_id=0):
    url = (
        f"{SERVER1_BASE_URL}/servers/{server_guid}/cameras/"
        f"{camera_id}/streams/{stream_id}/remote-url"
    )
    response = get(url, headers=HEADERS)
    if not response:
        return {}

    data = response.json()
    return {
        "url": data.get("url"),
        "username": data.get("username"),
        "password": data.get("password"),
    }


def run_discovery_flow():
    servers = get_servers()
    for server in servers:
        print(f"\nServer: {server['name']}")
        cameras = get_cameras_by_server(server["guid"])
        for camera in cameras:
            print(f"  Camera: {camera['name']}")
            try:
                stream_id = get_stream_id(server["guid"], camera["id"])
                if stream_id is None:
                    print("    [No stream ID found]")
                    continue

                stream_data = get_remote_url(
                    server["guid"], camera["id"], stream_id
                )
                print(f"    URL: {stream_data.get('url')}")
                print(f"    Username: {stream_data.get('username')}")
                print(f"    Password: {stream_data.get('password')}")
            except Exception as e:
                print(f"    [Error fetching stream]: {e}")


run_discovery_flow()
 """
