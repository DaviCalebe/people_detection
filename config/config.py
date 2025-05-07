from scripts.getToken import token

username = 'admin'
password = 'Magnum@2023'
IP = '10.10.50.6'
port = '554'
channel = '7'
CONFIDENCE_THRESHOLD = 0.2

RTSP_URL = (
    'rtsp://{}:{}@{}:{}/cam/realmonitor?channel={}&subtype=0'.format(
        username, password, IP, port, channel
    )
)

RTSP_VILA_VELHA = (
    "rtsp://192.168.65.23:80/cam/realmonitor?channel=1&subtype=0"
)

SERVER1_BASE_URL = 'http://10.10.50.180:7102/api'
SERVER2_BASE_URL = 'http://10.10.50.180:7102/api'

HEADERS = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}
