import sqlite3
import subprocess
import threading
import time
import cv2
import json
import numpy as np
from urllib.parse import urlparse, urlunparse
from ultralytics import YOLO
from events.scheduler import set_event_schedule

CONFIDENCE_THRESHOLD = 0.5
RESIZE_WIDTH = 640
RESIZE_HEIGHT = 360
PROCESS_EVERY = 5
event_delay = 30

model = YOLO('models/yolov8n.pt')


def insert_rtsp_credentials(url_base, username, password):
    parsed = urlparse(url_base)
    netloc = f"{username}:{password}@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


def get_rtsp_resolution(rtsp_url):
    cmd = [
        "C:\\ffmpeg\\bin\\ffprobe.exe", "-v", "error", "-select_streams", "v:0",
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
            if len(raw_frame) != frame_size:
                continue  # Pula frames incompletos (geralmente no fim da transmissão)

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
    def __init__(self, rtsp_url, camera_name, camera_id, dguard_camera_id, recorder_guid):
        super().__init__()
        self.rtsp_url = rtsp_url
        self.camera_name = camera_name
        self.camera_id = camera_id
        self.dguard_camera_id = dguard_camera_id
        self.recorder_guid = recorder_guid
        self.running = True

    def run(self):
        resolution = get_rtsp_resolution(self.rtsp_url)
        if not resolution:
            print(f"Erro ao obter resolução do RTSP para a câmera {self.camera_name}.")
            return

        width, height = resolution
        ffmpeg_cmd = [
            "C:\\ffmpeg\\bin\\ffmpeg.exe", "-fflags", "nobuffer", "-flags", "low_delay", "-strict", "experimental",
            "-rtsp_transport", "tcp", "-i", self.rtsp_url, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"
        ]
        proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, bufsize=10**8)
        freshest = FreshestFFmpegFrame(proc, width, height)

        frame_count = 0
        last_sent = 0
        start_time = time.time()

        while self.running and (time.time() - start_time < 20):
            frame = freshest.read()
            if frame is None:
                continue

            frame_count += 1
            resized = cv2.resize(frame, (RESIZE_WIDTH, RESIZE_HEIGHT))

            if frame_count % PROCESS_EVERY != 0:
                cv2.imshow(f'{self.camera_name}', resized)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                continue

            result = model(resized, classes=[0], verbose=False)

            person_detected = False
            total_detections = 0

            for objects in result:
                for data in objects.boxes:
                    conf = float(data.conf[0])
                    cls_id = int(data.cls[0])
                    label = model.names[cls_id]

                    if label != 'person' or conf < CONFIDENCE_THRESHOLD:
                        continue

                    x1, y1, x2, y2 = map(int, data.xyxy[0])
                    cv2.rectangle(resized, (x1, y1), (x2, y2), (251, 226, 0), 5)
                    cv2.putText(resized, f'{label} {conf:.2f}', (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (251, 226, 0), 2)
                    person_detected = True
                    total_detections += 1

            print(f"[INFO] Detecções ({self.camera_name}): {total_detections}")

            if person_detected:
                current_time = time.time()
                if current_time - last_sent >= event_delay:
                    print(f"[ALERTA] Pessoa detectada! ({self.camera_name})")
                    set_event_schedule(self.dguard_camera_id, self.recorder_guid)
                    last_sent = current_time

            cv2.imshow(f'{self.camera_name}', resized)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        freshest.stop()


def get_selected_cameras(camera_recorder_list):
    """
    camera_recorder_list: list of tuples (camera_id:int, recorder_guid:str)
    Retorna dados completos das câmeras (RTSP, nome, etc) do banco para as câmeras solicitadas.
    """
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if not camera_recorder_list:
        return []

    or_clauses = []
    params = []
    for cam_id, rec_guid in camera_recorder_list:
        or_clauses.append("(c.camera_id = ? AND r.guid = ?)")
        params.extend([cam_id, rec_guid])

    query = f"""
        SELECT c.id, c.camera_id AS dguard_camera_id, c.name, s.url, s.username, s.password, r.guid
        FROM cameras c
        JOIN streams s ON s.camera_id = c.id AND s.stream_id = 0
        JOIN recorders r ON c.recorder_id = r.id
        WHERE {" OR ".join(or_clauses)} AND s.url != 'indisponível'
    """

    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    return results


def start_monitoring_cameras(camera_recorder_list):
    """
    camera_recorder_list: list of tuples (camera_id:int, recorder_guid:str)
    Inicia threads para monitorar cada câmera.
    Retorna lista de threads iniciadas.
    """
    cameras = get_selected_cameras(camera_recorder_list)
    threads = []

    for (camera_id, dguard_camera_id, camera_name, rtsp_url, username, password, recorder_guid) in cameras:
        full_rtsp_url = insert_rtsp_credentials(rtsp_url, username, password)
        thread = CameraThread(full_rtsp_url, camera_name, camera_id, dguard_camera_id, recorder_guid)
        thread.start()
        threads.append(thread)

    return threads
