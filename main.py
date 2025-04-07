import cv2
import requests
from ultralytics import YOLO

username = 'admin'
password = 'Magnum@2023'
IP = '10.10.50.241'
port = '554'
channel = '6'
CONFIDENCE_THRESHOLD = 0.2
model = YOLO('yolov8n.pt')

""" login_url = "https://10.10.50.181:7101/#!/login"

credentials = {
    "username": "TesteAPI",
    "password": "Teste.1"
}

res = requests.post(login_url, json=credentials)
token = res.json()['token'] """

token = "eyJ1c2VyTmFtZSI6IlRlc3RlQVBJIn0.3r7jwKtIvO5rAgeCjXGOY_6NEs49YhMg9olrqMwDv1s"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}


def send_event():
    url = "https://10.10.50.181:7101/api/custom-events"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "name": "TESTANDO 9090",
        "type": 1
        }
    response = requests.post(url, headers=headers, json=data, verify=False)
    if response.status_code == 200:
        print("✅ Evento enviado ao D-Guard")
    else:
        print("❌ Falha ao enviar evento:", response.text)


URL = (
    'rtsp://{}:{}@{}:{}/cam/realmonitor?channel={}&subtype=0'.format(
        username, password, IP, port, channel
    )
)

""" URL = "./andre-mariano-nosemanual.mp4"
 """

cap = cv2.VideoCapture(URL)

if not cap.isOpened():
    print("Erro ao abrir o vídeo!")
    exit()

while True:
    ret, frame = cap.read()
    if not ret:
        print("Sem frame")
        break

    result = model(frame)
    for objects in result:
        obj = objects.boxes
        for data in obj:
            conf = float(data.conf[0])
            cls_id = int(data.cls[0])
            conf = float(data.conf[0])
            label = model.names[cls_id]

            if label != 'person' or conf < CONFIDENCE_THRESHOLD:
                continue
            x, y, w, h = data.xyxy[0]
            x, y, w, h = int(x), int(y), int(w), int(h)

            cv2.rectangle(frame, (x, y), (w, h), (251, 226, 0), 5)

            text = f'{label} {conf:.2f}'
            cv2.putText(frame, text, (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (251, 226, 0), 2)

            send_event()
            break

    cv2.imshow('VIDEO', frame)

    if cv2.waitKey(25) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
