import json
import time
import cv2
import subprocess
import numpy as np
import threading
import argparse
import sqlite3
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


def get_selected_cameras(camera_ids=None):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    selected = []

    if camera_ids:
        placeholders = ','.join('?' * len(camera_ids))
        cursor.execute(f"""
            SELECT c.id, c.camera_id AS dguard_camera_id, c.name, s.url, s.username, s.password, r.guid
            FROM cameras c
            JOIN streams s ON s.camera_id = c.id AND s.stream_id = 0
            JOIN recorders r ON c.recorder_id = r.id
            WHERE c.id IN ({placeholders}) AND s.url != 'indisponível'
        """, tuple(camera_ids))
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
            "ffmpeg", "-fflags", "nobuffer", "-flags", "low_delay", "-strict", "experimental",
            "-rtsp_transport", "tcp", "-i", self.rtsp_url, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"
        ]
        proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, bufsize=10**8)
        freshest = FreshestFFmpegFrame(proc, width, height)

        frame_count = 0
        last_sent = 0

        while self.running:
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


def parse_arguments():
    parser = argparse.ArgumentParser(description="Selecionar câmeras para monitoramento")
    parser.add_argument('--camera-id', nargs='+', type=int, help='IDs das câmeras específicas')
    return parser.parse_args()


def interactive_selection():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # Etapa 1: escolher o servidor
    cursor.execute("SELECT name FROM servers")
    servers = [row[0] for row in cursor.fetchall()]
    print("\nServidores disponíveis:")
    for i, s in enumerate(servers, 1):
        print(f"{i}. {s}")

    server_idx = int(input("Escolha o número do servidor: ")) - 1
    selected_server = servers[server_idx]

    # Etapa 2: escolher os gravadores
    cursor.execute("SELECT name FROM recorders WHERE server_id = (SELECT id FROM servers WHERE name = ?)", (selected_server,))
    recorders = [row[0] for row in cursor.fetchall()]
    print("\nGravadores disponíveis:")
    for i, r in enumerate(recorders, 1):
        print(f"{i}. {r}")
    print("0. Todos")

    recorder_input = input("Escolha os números dos gravadores (separados por espaço): ")
    if recorder_input.strip() == "0":
        selected_recorders = recorders
    else:
        selected_indexes = [int(i)-1 for i in recorder_input.split()]
        selected_recorders = [recorders[i] for i in selected_indexes]

    # Etapa 3: escolher câmeras
    placeholders = ','.join('?' * len(selected_recorders))
    cursor.execute(f"""
        SELECT c.id, c.name FROM cameras c
        JOIN recorders r ON c.recorder_id = r.id
        WHERE r.name IN ({placeholders})
    """, tuple(selected_recorders))
    camera_rows = cursor.fetchall()

    cameras = [name for _, name in camera_rows]
    camera_ids = [cid for cid, _ in camera_rows]

    print("\nCâmeras disponíveis:")
    for i, (cid, name) in enumerate(camera_rows, 1):
        print(f"{i}. ID {cid} - {name}")
    print("0. Todas")

    camera_input = input("Escolha os números das câmeras (separados por espaço): ")
    if camera_input.strip() == "0":
        selected_camera_ids = camera_ids
    else:
        selected_indexes = [int(i)-1 for i in camera_input.split()]
        selected_camera_ids = [camera_ids[i] for i in selected_indexes]

    selected_camera_names = [cameras[i] for i in selected_indexes] if camera_input.strip() != "0" else cameras
    conn.close()

    return selected_camera_ids, selected_camera_names


def main():
    args = parse_arguments()

    if not args.camera_id:
        # Modo interativo
        selected_camera_ids, selected_camera_names = interactive_selection()
    else:
        selected_camera_ids = args.camera_id
        selected_camera_names = [f"Camera {cid}" for cid in selected_camera_ids]

    cameras_to_monitor = get_selected_cameras(camera_ids=selected_camera_ids)

    if not cameras_to_monitor:
        print("Nenhuma câmera válida selecionada.")
        return

    threads = []
    for (camera_id, dguard_camera_id, camera_name, rtsp_url, username, password, recorder_guid) in cameras_to_monitor:
        full_rtsp_url = insert_rtsp_credentials(rtsp_url, username, password)
        thread = CameraThread(full_rtsp_url, camera_name, camera_id, dguard_camera_id, recorder_guid)
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
