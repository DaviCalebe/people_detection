import time
import cv2
import requests
from ultralytics import YOLO
from datetime import datetime, timedelta
from config.config import (
    CONFIDENCE_THRESHOLD,
    RTSP_URL,
    HEADERS,
    SERVER1_BASE_URL
)
from scripts.guids import PEOPLE_DETECTION_EVENT

model = YOLO('models/yolov8n.pt')

last_sent = 0
event_delay = 30
now = datetime.now()
scheduled_time = now + timedelta(minutes=10)
formatted_time = scheduled_time.strftime("%H:%M:%S")


def set_event_schedule():
    url = (
        f"{SERVER1_BASE_URL}/custom-events/"
        f"{PEOPLE_DETECTION_EVENT}/scheduled-times"
    )

    data = {
        "scheduledTime": formatted_time
    }

    response = requests.post(
        url, headers=HEADERS, json=data, verify=False
    )

    if response.status_code == 200:
        print("Evento agendado com sucesso!")
    else:
        print(
            f"Erro ao agendar evento: "
            f"{response.status_code} - {response.text}"
        )

    return response


cap = cv2.VideoCapture(RTSP_URL)

if not cap.isOpened():
    print("Erro ao abrir o vídeo!")
    exit()

while True:
    ret, frame = cap.read()
    if not ret:
        print("Sem frame")
        break

    result = model(frame, classes=[0], verbose=False)
    for objects in result:
        obj = objects.boxes
        for data in obj:
            conf = float(data.conf[0])
            cls_id = int(data.cls[0])
            label = model.names[cls_id]

            if label != 'person' or conf < CONFIDENCE_THRESHOLD:
                continue

            x, y, w, h = data.xyxy[0]
            x, y, w, h = int(x), int(y), int(w), int(h)

            cv2.rectangle(frame, (x, y), (w, h), (251, 226, 0), 5)

            text = f'{label} {conf:.2f}'
            cv2.putText(
                frame, text, (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (251, 226, 0), 2
            )

            current_time = time.time()
            if current_time - last_sent >= event_delay:
                set_event_schedule()
                last_sent = current_time

    cv2.imshow('VIDEO', frame)

    if cv2.waitKey(25) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
