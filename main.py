import time
import cv2
import subprocess
import numpy as np
import json
import threading
from ultralytics import YOLO
from config.config import CONFIDENCE_THRESHOLD, RTSP_URL
from events.scheduler import set_event_schedule

# YOLOv8 modelo leve
model = YOLO('models/yolov8n.pt')
event_delay = 30  # segundos entre eventos

RESIZE_WIDTH = 640
RESIZE_HEIGHT = 360
process_every = 5


def get_rtsp_resolution(rtsp_url):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json", rtsp_url
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print("Erro ao executar ffprobe:", result.stderr)
        return None
    try:
        info = json.loads(result.stdout)
        return info["streams"][0]["width"], info["streams"][0]["height"]
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
        frame_size = self.width * self.height * 3
        while self.running:
            raw_frame = self.proc.stdout.read(frame_size)
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
    frame_count = 0

    # Linha virtual na resolução redimensionada
    line_x = RESIZE_WIDTH // 2
    line_start = (line_x, 0)
    line_end = (line_x, RESIZE_HEIGHT)

    ffmpeg_cmd = [
        "ffmpeg",
        "-fflags", "nobuffer",
        "-flags", "low_delay",
        "-strict", "experimental",
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

            frame_count += 1
            resized = cv2.resize(frame, (RESIZE_WIDTH, RESIZE_HEIGHT))

            # Desenha linha virtual
            cv2.line(resized, line_start, line_end, (0, 0, 255), 2)

            if frame_count % process_every != 0:
                cv2.imshow('VIDEO', resized)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                continue

            start_time = time.time()
            result = model(resized, classes=[0], verbose=False)
            processing_time = time.time() - start_time
            print(f"[INFO] Tempo de inferência YOLO: {processing_time:.3f} segundos")

            person_detected_right = False
            total_detections = 0

            for objects in result:
                for i, data in enumerate(objects.boxes):
                    conf = float(data.conf[0])
                    cls_id = int(data.cls[0])
                    label = model.names[cls_id]

                    if label != 'person' or conf < CONFIDENCE_THRESHOLD:
                        continue

                    x1, y1, x2, y2 = map(int, data.xyxy[0])
                    cx = int((x1 + x2) // 2)

                    if cx > line_x:
                        person_detected_right = True
                        cv2.rectangle(resized, (x1, y1), (x2, y2), (251, 226, 0), 5)
                        cv2.putText(resized, f'{label} {conf:.2f}', (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (251, 226, 0), 2)
                        cv2.circle(resized, (cx, (y1 + y2) // 2), 5, (255, 0, 0), -1)

                    total_detections += 1

            print(f"[INFO] Detecções: {total_detections}")

            if person_detected_right:
                current_time = time.time()
                if current_time - last_sent >= event_delay:
                    print("[ALERTA] Pessoa detectada à direita da linha!")
                    set_event_schedule()
                    last_sent = current_time

            cv2.imshow('VIDEO', resized)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        freshest.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
