import time
import cv2
import requests
import subprocess
import numpy as np
import json
from ultralytics import YOLO
from datetime import datetime, timedelta
from config.config import (
    CONFIDENCE_THRESHOLD,
    RTSP_URL,
    HEADERS,
)
from scripts.server2_guids import S2_PEOPLE_DETECTION_EVENT, SERVER2_BASE_URL

model = YOLO('models/yolov8n.pt')
model.to('cuda')
event_delay = 30


def set_event_schedule():
    now = datetime.now()
    scheduled_time = now - timedelta(minutes=1)
    formatted_time = scheduled_time.strftime("%H:%M:%S")
    url = (
        f"{SERVER2_BASE_URL}/custom-events/"
        f"{S2_PEOPLE_DETECTION_EVENT}/scheduled-times"
    )

    data = {
        "scheduledTime": formatted_time
    }

    response = requests.post(
        url, headers=HEADERS, json=data, verify=False
    )

    if response.status_code in (200, 201):
        print("Evento agendado com sucesso! Time sent:", data)
    else:
        print(f"Erro ao agendar evento: {response.status_code} - {response.text} Time sent:", data)

    return response


def get_rtsp_resolution(rtsp_url):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        rtsp_url
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        print("Erro ao executar ffprobe:", result.stderr)
        return None

    try:
        info = json.loads(result.stdout)
        width = info["streams"][0]["width"]
        height = info["streams"][0]["height"]
        return width, height
    except (KeyError, IndexError):
        print("Não foi possível extrair resolução.")
        return None


def main():
    resolution = get_rtsp_resolution(RTSP_URL)
    if not resolution:
        print("Erro ao obter resolução do RTSP.")
        return

    width, height = resolution
    last_sent = 0
    event_delay = 30

    ffmpeg_cmd = [
        "ffmpeg",
        "-rtsp_transport", "tcp",
        "-i", RTSP_URL,
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-"
    ]

    proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, bufsize=10**8)

    while True:
        raw_frame = proc.stdout.read(width * height * 3)
        if not raw_frame:
            print("Frame vazio ou fim do stream.")
            break

        frame = np.frombuffer(raw_frame, np.uint8).reshape((height, width, 3))

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
                    last_sent
                    last_sent = current_time

        cv2.imshow('VIDEO', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    proc.terminate()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
