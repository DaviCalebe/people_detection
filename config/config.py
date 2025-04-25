from people_detection.scripts.getToken import token

username = 'admin'
password = 'Magnum@2023'
IP = '10.10.50.241'
port = '554'
channel = '6'
CONFIDENCE_THRESHOLD = 0.2

RTSP_URL = (
    'rtsp://{}:{}@{}:{}/cam/realmonitor?channel={}&subtype=0'.format(
        username, password, IP, port, channel
    )
)

SERVER1 = 'https://10.10.50.181:7101'

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}
