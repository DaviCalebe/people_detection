import time
from ultralytics import YOLO
from config import CONFIDENCE_THRESHOLD, RTSP_URL, token
import cv2
import requests

model = YOLO('yolov8n.pt')

last_sent = 0
event_delay = 30


def send_event():
    url = "https://10.10.50.181:7101/api/custom-events"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "name": "TESTANDO DE NOVO",
        "type": 1
        }
    response = requests.post(url, headers=headers, json=data, verify=False)
    if response.status_code == 200:
        print("✅ Evento enviado ao D-Guard")
    else:
        print("❌ Falha ao enviar evento:", response.text)


cap = cv2.VideoCapture(RTSP_URL)

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

            current_time = time.time()
            if current_time - last_sent >= event_delay:
                send_event()
                last_sent = current_time

    cv2.imshow('VIDEO', frame)

    if cv2.waitKey(25) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
