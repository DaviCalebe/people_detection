import json
import time
import cv2
import subprocess
import numpy as np
import threading
import argparse
import sqlite3
from ultralytics import YOLO
from events.scheduler import set_event_schedule

CONFIDENCE_THRESHOLD = 0.5
RESIZE_WIDTH = 640
RESIZE_HEIGHT = 360
PROCESS_EVERY = 5
event_delay = 30

model = YOLO('models/yolov8n.pt')


def get_selected_cameras(server=None, recorders=None, cameras=None):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    selected = []

    if server:
        cursor.execute("""
            SELECT c.name, s.url FROM cameras c
            JOIN recorders r ON c.recorder_id = r.id
            JOIN servers sr ON r.server_id = sr.id
            JOIN streams s ON s.camera_id = c.id AND s.stream_id = 0
            WHERE sr.name = ? AND s.url != 'indisponível'""", (server,))
        selected = cursor.fetchall()

    elif recorders:
        placeholders = ','.join('?' * len(recorders))
        cursor.execute(f"""
            SELECT c.name, s.url FROM cameras c
            JOIN recorders r ON c.recorder_id = r.id
            JOIN streams s ON s.camera_id = c.id AND s.stream_id = 0
            WHERE r.name IN ({placeholders}) AND s.url != 'indisponível'""", tuple(recorders))
        selected = cursor.fetchall()

    elif cameras:
        placeholders = ','.join('?' * len(cameras))
        cursor.execute(f"""
            SELECT c.name, s.url FROM cameras c
            JOIN streams s ON s.camera_id = c.id AND s.stream_id = 0
            WHERE c.name IN ({placeholders}) AND s.url != 'indisponível'""", tuple(cameras))
        selected = cursor.fetchall()

    conn.close()
    return selected


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


class CameraThread(threading.Thread):
    def __init__(self, rtsp_url, camera_name):
        super().__init__()
        self.rtsp_url = rtsp_url
        self.camera_name = camera_name
        self.running = True

    def run(self):
        resolution = get_rtsp_resolution(self.rtsp_url)
        if not resolution:
            print(f"Erro ao obter resolução do RTSP para a câmera {self.camera_name}.")
            return

        width, height = resolution
        ffmpeg_cmd = [
            "ffmpeg", "-fflags", "nobuffer", "-flags", "low_delay", "-strict", "experimental",
            "-rtsp_transport", "tcp", "-i", self.rtsp_url, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"
        ]
        proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, bufsize=10**8)
        freshest = FreshestFFmpegFrame(proc, width, height)

        line_x = RESIZE_WIDTH // 2
        line_start = (line_x, 0)
        line_end = (line_x, RESIZE_HEIGHT)

        frame_count = 0
        last_sent = 0

        while self.running:
            frame = freshest.read()
            if frame is None:
                continue

            frame_count += 1
            resized = cv2.resize(frame, (RESIZE_WIDTH, RESIZE_HEIGHT))

            cv2.line(resized, line_start, line_end, (0, 0, 255), 2)

            if frame_count % PROCESS_EVERY != 0:
                cv2.imshow(f'{self.camera_name}', resized)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                continue

            result = model(resized, classes=[0], verbose=False)

            person_detected_right = False
            total_detections = 0

            for objects in result:
                for data in objects.boxes:
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

            print(f"[INFO] Detecções ({self.camera_name}): {total_detections}")

            if person_detected_right:
                current_time = time.time()
                if current_time - last_sent >= event_delay:
                    print(f"[ALERTA] Pessoa detectada à direita da linha! ({self.camera_name})")
                    set_event_schedule()
                    last_sent = current_time

            cv2.imshow(f'{self.camera_name}', resized)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        freshest.stop()


def parse_arguments():
    parser = argparse.ArgumentParser(description="Selecionar câmeras para monitoramento")
    parser.add_argument('--server', help='Nome do servidor (ex: server1)')
    parser.add_argument('--recorder', nargs='+', help='Nome(s) dos gravadores específicos')
    parser.add_argument('--camera', nargs='+', help='Nome(s) das câmeras específicas')
    return parser.parse_args()


def main():
    args = parse_arguments()
    selected_cameras = get_selected_cameras(
        server=args.server,
        recorders=args.recorder,
        cameras=args.camera
    )

    if not selected_cameras:
        print("Nenhuma câmera válida selecionada.")
        return

    threads = []
    for camera_name, rtsp_url in selected_cameras:
        thread = CameraThread(rtsp_url, camera_name)
        thread.start()
        threads.append(thread)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Encerrando...")
        for thread in threads:
            thread.running = False
            thread.join()

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
