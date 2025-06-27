import sqlite3
import subprocess
import threading
import time
import cv2
import json
import os
import logging
import numpy as np
from datetime import datetime
from urllib.parse import urlparse, urlunparse
from ast import literal_eval
from ultralytics import YOLO
from events.scheduler import set_event_schedule

# Caminho para salvar os logs fora do projeto
log_dir = r"C:\Users\suporte\Documents\Logs-Deteccao"
os.makedirs(log_dir, exist_ok=True)  # Cria a pasta se não existir

# Configurar o nome do arquivo de log com data/hora
log_filename = os.path.join(log_dir, f"logs_{datetime.now().strftime('%d-%m-%Y')}.txt")

# Criar o logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Criar formatador com timestamp
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')

# Handler para arquivo
file_handler = logging.FileHandler(log_filename, encoding='utf-8')
file_handler.setFormatter(formatter)

# Handler para terminal
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# Adicionar os handlers ao logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Substituir print por logging.info (ou warning/error etc)
print = logger.info  # Redireciona todos os print() para logging.info()

CONFIDENCE_THRESHOLD = 0.5
RESIZE_WIDTH = 640
RESIZE_HEIGHT = 360
PROCESS_EVERY = 5
event_delay = 30

model = YOLO('models/yolov8n.pt')

# --- Carregar ZONES do arquivo JSON com keys convertidas para tupla
with open('zones.json', 'r') as f:
    raw = json.load(f)
    ZONES = {literal_eval(k): v for k, v in raw.items()}


def is_in_zone(center, config):
    cx, cy = center

    if config["type"] == "side":
        (x1, y1), (x2, y2) = config["line"]

        # Vetor da linha
        dx = x2 - x1
        dy = y2 - y1

        # Vetor do ponto em relação ao ponto inicial da linha
        dxp = cx - x1
        dyp = cy - y1

        # Produto vetorial (para saber de que lado da linha está)
        cross = dx * dyp - dy * dxp

        # Definir lado com base na direção do vetor
        if config["side"] == "left":
            resultado = cross > 0
            return resultado
        elif config["side"] == "right":
            resultado = cross < 0
            return resultado
        elif config["side"] == "top":
            resultado = cross > 0 if dy == 0 else cy < y1
            return resultado
        elif config["side"] == "bottom":
            resultado = cross < 0 if dy == 0 else cy > y1
            return resultado

        print("[DEBUG] Nenhum lado válido encontrado, retornando False")
        return False

    elif config["type"] == "area":
        polygon = np.array(config["polygon"], np.int32)
        inside = cv2.pointPolygonTest(polygon, (cx, cy), False) >= 0
        return inside

    print("[DEBUG] Tipo desconhecido, retornando False")
    return False


def insert_rtsp_credentials(url_base, username, password):
    parsed = urlparse(url_base)
    netloc = f"{username}:{password}@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


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
    def __init__(self, rtsp_url, camera_name, camera_id, dguard_camera_id, recorder_guid, recorder_name):
        super().__init__()
        self.rtsp_url = rtsp_url
        self.camera_name = camera_name
        self.camera_id = camera_id
        self.dguard_camera_id = dguard_camera_id
        self.recorder_guid = recorder_guid
        self.recorder_name = recorder_name
        self.running = True

    def run(self):
        resolution = get_rtsp_resolution(self.rtsp_url)
        if not resolution:
            print(f"Erro ao obter resolução do RTSP para a câmera {self.camera_name} ({self.recorder_name}).")
            return

        width, height = resolution
        ffmpeg_cmd = [
            "ffmpeg", "-loglevel", "error", "-fflags", "nobuffer", "-flags", "low_delay", "-strict", "experimental",
            "-rtsp_transport", "tcp", "-i", self.rtsp_url, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"
        ]

        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10**8,
            text=False
        )

        freshest = FreshestFFmpegFrame(proc, width, height)

        def log_ffmpeg_errors(stderr_pipe, camera_name, recorder_name):
            pps_error_detected = False

            for line in iter(stderr_pipe.readline, b''):
                decoded_line = line.decode('utf-8', errors='ignore').strip()

                if "non-existing PPS" in decoded_line:
                    if not pps_error_detected:
                        logger.error(f"{camera_name} ({recorder_name}): PPS ausente no stream RTSP. Ignorando mensagens repetidas.")
                        pps_error_detected = True
                    continue

                if pps_error_detected and any(x in decoded_line for x in [
                    "decode_slice_header error",
                    "no frame!",
                    "Error submitting packet",
                    "Invalid data found"
                ]):
                    continue

                logger.error(f"{camera_name} ({recorder_name}) {decoded_line}")

        error_thread = threading.Thread(
            target=log_ffmpeg_errors,
            args=(proc.stderr, self.camera_name, self.recorder_name),
            daemon=True
        )
        error_thread.start()

        frame_count = 0
        last_sent = 0
        start_time = time.time()
        person_detected = False
        last_total_detections = 0

        while self.running and (time.time() - start_time < 20):
            frame = freshest.read()
            if frame is None:
                continue

            frame_count += 1
            resized = cv2.resize(frame, (RESIZE_WIDTH, RESIZE_HEIGHT))

            if frame_count % PROCESS_EVERY != 0:
                # Desabilitado: Exibição do vídeo ao vivo
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
                    center = ((x1 + x2) // 2, (y1 + y2) // 2)

                    zone_config = ZONES.get((self.dguard_camera_id, self.recorder_guid))

                    if zone_config and not is_in_zone(center, zone_config):
                        continue  # Ignorar se fora da zona

                    # Desabilitado: Desenho de caixas e texto no frame
                    cv2.rectangle(resized, (x1, y1), (x2, y2), (251, 226, 0), 5)
                    cv2.putText(resized, f'{label} {conf:.2f}', (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (251, 226, 0), 2)
                    person_detected = True
                    total_detections += 1

            if total_detections != last_total_detections:
                last_total_detections = total_detections

            if person_detected:
                current_time = time.time()
                if current_time - last_sent >= event_delay:
                    print(f"[WARNING] Pessoa detectada! ({self.camera_name} - {self.recorder_name})")
                    set_event_schedule(self.dguard_camera_id, self.recorder_guid)
                    last_sent = current_time
                break

            # Desabilitado: Exibição do frame processado
            cv2.imshow(f'{self.camera_name}', resized)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        freshest.stop()

        if person_detected:
            print(f"DETECÇÃO REALIZADA para {self.camera_name} ({self.recorder_name})")
        else:
            print(f"NENHUMA DETECÇÃO para {self.camera_name} ({self.recorder_name})")


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
        SELECT
            c.id,
            c.camera_id AS dguard_camera_id,
            c.name,
            s.url,
            s.username,
            s.password,
            r.guid,
            r.name AS recorder_name
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

    for (camera_id, dguard_camera_id, camera_name, rtsp_url, username, password, recorder_guid, recorder_name) in cameras:
        full_rtsp_url = insert_rtsp_credentials(rtsp_url, username, password)
        thread = CameraThread(full_rtsp_url, camera_name, camera_id, dguard_camera_id, recorder_guid, recorder_name)
        print(f"Iniciando thread para câmera: {camera_name} ({recorder_name})")
        thread.start()
        threads.append(thread)

    return threads
