import time
import cv2
import requests
import subprocess
import numpy as np
import json
import threading
from ultralytics import YOLO
from datetime import datetime, timedelta
from config.config import (
    CONFIDENCE_THRESHOLD,
    RTSP_URL,
    HEADERS,
)
from scripts.server2_guids import S2_PEOPLE_DETECTION_EVENT, SERVER2_BASE_URL

model = YOLO('models/yolov8n.pt')
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


class FreshestFFmpegFrame(threading.Thread):
    def __init__(self, ffmpeg_proc, width, height):
        super().__init__()
        self.proc = ffmpeg_proc
        self.width = width
        self.height = height
        self.frame = None
        self.lock = threading.Lock()
        self.running = True
        self.start()

    def run(self):
        while self.running:
            raw_frame = self.proc.stdout.read(self.width * self.height * 3)
            if not raw_frame:
                break
            frame = np.frombuffer(raw_frame, np.uint8).reshape((self.height, self.width, 3))
            with self.lock:
                self.frame = frame

    def read(self):
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    def stop(self):
        self.running = False
        self.proc.terminate()
        self.join()


def main():
    resolution = get_rtsp_resolution(RTSP_URL)
    if not resolution:
        print("Erro ao obter resolução do RTSP.")
        return

    width, height = resolution
    last_sent = 0

    ffmpeg_cmd = [
        "ffmpeg",
        "-rtsp_transport", "tcp",
        "-i", RTSP_URL,
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-"
    ]

    proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, bufsize=10**8)
    freshest = FreshestFFmpegFrame(proc, width, height)

    try:
        while True:
            frame = freshest.read()
            if frame is None:
                continue

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
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        freshest.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
