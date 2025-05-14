from scripts.getToken import token

username = 'admin'
password = 'Magnum@2023'
IP = '10.10.50.6'
port = '554'
channel = '15'
CONFIDENCE_THRESHOLD = 0.5

RTSP_URL_1 = (
    'rtsp://admin:Magnum@2023@10.10.50.6:554/cam/realmonitor?channel=15&subtype=0'.format(
        username, password
    )
)

RTSP_URL_2 = (
    'rtsp://admin:Magnum@2023@10.10.50.6:554/cam/realmonitor?channel=14&subtype=0'.format(
        username, password
    )
)

RTSP_VILA_VELHA = (
    "rtsp://dguard:monitoramento@CFTV2024@192.168.65.23:80/cam/realmonitor?channel=1&subtype=0"
)


HEADERS = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}
