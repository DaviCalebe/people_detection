username = 'admin'
password = 'Magnum@2023'
IP = '10.10.50.241'
port = '554'
channel = '6'
CONFIDENCE_THRESHOLD = 0.2

token = "eyJ1c2VyTmFtZSI6IlRlc3RlQVBJIn0.3r7jwKtIvO5rAgeCjXGOY_6NEs49YhMg9olrqMwDv1s"

RSTP_URL = (
    'rtsp://{}:{}@{}:{}/cam/realmonitor?channel={}&subtype=0'.format(
        username, password, IP, port, channel
    )
)
