import sqlite3
import subprocess
import threading
import time
import cv2
import json
import os
import logging
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlparse, urlunparse
from ast import literal_eval
from ultralytics import YOLO
from events.scheduler import set_event_schedule

# Caminho para salvar os logs fora do projeto
log_dir = r"C:\Users\dcalebe\Documents\Logs-Deteccao"
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

SHOW_VIDEO = False
CONFIDENCE_THRESHOLD = 0.5
RESIZE_WIDTH = 640
RESIZE_HEIGHT = 360
PROCESS_EVERY = 5
event_delay = 30
MAX_ACTIVE_CAMERAS = 10

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


def get_rtsp_resolution(rtsp_url, camera_name=None, recorder_name=None):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json", rtsp_url
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except OSError as e:
        logger.error(f"[{camera_name} - {recorder_name}] Erro ao executar ffprobe (OSError): {e}")
        return None
    except Exception as e:
        logger.error(f"[{camera_name} - {recorder_name}] Erro inesperado ao executar ffprobe: {e}")
        return None


    if result.returncode != 0:
        logger.error(f"Erro ao executar ffprobe: {result.stderr.strip()}")
        return None

    try:
        info = json.loads(result.stdout)
        return info["streams"][0]["width"], info["streams"][0]["height"]
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        logger.error(f"Não foi possível extrair resolução: {e}")
        return None



def get_recorders():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, guid, name FROM recorders")
    recorders = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "guid": r[1], "name": r[2]} for r in recorders]

def get_cameras_by_recorder(recorder_guid):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.camera_id, c.name, s.url, s.username, s.password
        FROM cameras c
        JOIN streams s ON s.camera_id = c.id
        JOIN recorders r ON c.recorder_id = r.id
        WHERE r.guid = ?
    """, (recorder_guid,))
    cameras = cursor.fetchall()
    conn.close()
    return [
        {
            "id": c[0],
            "camera_id": c[1],
            "name": c[2],
            "url": c[3],
            "username": c[4],
            "password": c[5]
        } for c in cameras
    ]


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
                continue  # Pula frames incompletos

            frame = np.frombuffer(raw_frame, np.uint8).reshape((self.height, self.width, 3))
            with self.lock:
                self.frame = frame

    def read(self):
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    def stop(self):
        self.running = False
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
        self.error_event_sent = False
        self.ffmpeg_proc = None
        self.freshest = None
        self.error_thread = None

    def trigger_error_event(self, reason):
        if not self.error_event_sent:
            logger.warning(f"[{self.camera_name} - {self.recorder_name}] Acionando evento por erro: {reason}")
            set_event_schedule(self.dguard_camera_id, self.recorder_guid)
            self.error_event_sent = True

    def stop(self):
        """Para toda a stack da câmera: loop, Freshest, FFmpeg e janela OpenCV."""
        self.running = False

        if self.freshest:
            self.freshest.stop()

        if self.ffmpeg_proc and self.ffmpeg_proc.poll() is None:
            try:
                self.ffmpeg_proc.terminate()
                self.ffmpeg_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.ffmpeg_proc.kill()

        if SHOW_VIDEO:
            try:
                cv2.destroyWindow(f"{self.camera_name}")
            except:
                pass

        logger.info(f"[{self.camera_name} - {self.recorder_name}] CameraThread finalizada com sucesso.")



    def _log_ffmpeg_errors(self, stderr_pipe):
        pps_error_detected = False
        ref_error_detected = False
        disconnect_error_detected = False

        for line in iter(stderr_pipe.readline, b''):
            decoded_line = line.decode('utf-8', errors='ignore').strip()

            if "non-existing PPS" in decoded_line:
                if not pps_error_detected:
                    logger.error(f"{self.camera_name} ({self.recorder_name}): PPS ausente no stream RTSP.")
                    pps_error_detected = True
                continue

            if pps_error_detected and any(x in decoded_line for x in [
                "decode_slice_header error",
                "no frame!",
                "Error submitting packet",
                "Invalid data found"
            ]):
                continue

            if "reference picture missing" in decoded_line or "Missing reference picture" in decoded_line:
                if not ref_error_detected:
                    logger.error(f"{self.camera_name} ({self.recorder_name}): Referência de frame ausente.")
                    ref_error_detected = True
                continue

            if ref_error_detected and any(x in decoded_line for x in [
                "decode_slice_header error",
                "bytestream",
                "Missing reference picture",
                "no frame!",
                "Invalid data found"
            ]):
                continue

            if "Error number -10054" in decoded_line:
                if not disconnect_error_detected:
                    logger.error(f"{self.camera_name} ({self.recorder_name}): Desconexão remota detectada (-10054).")
                    disconnect_error_detected = True
                    set_event_schedule(self.dguard_camera_id, self.recorder_guid)
                continue

            logger.error(f"{self.camera_name} ({self.recorder_name}) {decoded_line}")
            set_event_schedule(self.dguard_camera_id, self.recorder_guid)

    def run(self):
        resolution = get_rtsp_resolution(self.rtsp_url, self.camera_name, self.recorder_name)
        if not resolution:
            self.trigger_error_event("Failed to get RTSP resolution")
            return

        width, height = resolution
        ffmpeg_cmd = [
            "ffmpeg",
            "-loglevel", "error",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-rtsp_transport", "tcp",
            "-i", self.rtsp_url,
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-"
        ]

        self.ffmpeg_proc = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=4096,
            text=False
        )

        if self.ffmpeg_proc.stdout is None or self.ffmpeg_proc.stderr is None:
            self.trigger_error_event("FFmpeg não iniciou corretamente")
            return

        self.freshest = FreshestFFmpegFrame(self.ffmpeg_proc, width, height)

        self.error_thread = threading.Thread(
            target=self._log_ffmpeg_errors,
            args=(self.ffmpeg_proc.stderr,),
            daemon=True
        )
        self.error_thread.start()

        try:
            frame_count = 0
            last_sent = 0
            person_detected = False
            last_total_detections = 0
            thread_start_time = time.time()

            logger.debug(f"[{self.camera_name} - {self.recorder_name}] Entrando no loop de monitoramento.")

            while self.running and (time.time() - thread_start_time < 20):
                frame = self.freshest.read()
                if frame is None:
                    time.sleep(0.2)
                    continue

                frame_count += 1
                resized = cv2.resize(frame, (RESIZE_WIDTH, RESIZE_HEIGHT))

                if frame_count % PROCESS_EVERY != 0:
                    if SHOW_VIDEO:
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
                            continue

                        if SHOW_VIDEO:
                            cv2.rectangle(resized, (x1, y1), (x2, y2), (251, 226, 0), 5)
                            cv2.putText(resized, f'{label} {conf:.2f}', (x1, y1 - 10),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (251, 226, 0), 2)
                        person_detected = True
                        total_detections += 1

                if person_detected:
                    current_time = time.time()
                    if current_time - last_sent >= event_delay:
                        logger.warning(f"Pessoa detectada! ({self.camera_name} - {self.recorder_name})")
                        last_sent = current_time
                        set_event_schedule(self.dguard_camera_id, self.recorder_guid)
                    break

                if SHOW_VIDEO:
                    cv2.imshow(f'{self.camera_name}', resized)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

            status = "DETECÇÃO REALIZADA" if person_detected else "NENHUMA DETECÇÃO"
            logger.info(f"{status} para {self.camera_name} ({self.recorder_name})")

        except Exception as e:
            logger.exception(f"Erro inesperado em {self.camera_name} ({self.recorder_name}): {e}")
            self.trigger_error_event("Erro inesperado na thread da câmera")

        finally:
            self.stop()


def get_cameras_by_recorder_virtual(recorder_guid):
    """
    Retorna todas as câmeras de um gravador específico,
    usando apenas a stream extra (stream_id=1),
    prontas para iniciar um CameraThread.
    """
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    query = """
        SELECT
            c.id,
            c.camera_id,           -- mantém como camera_id
            c.name,
            s.url,
            s.username,
            s.password,
            r.guid AS recorder_guid,
            r.name AS recorder_name,
            s.stream_id
        FROM cameras c
        JOIN streams s ON s.camera_id = c.id AND s.stream_id = 1  -- apenas stream extra
        JOIN recorders r ON c.recorder_id = r.id
        WHERE r.guid = ? AND s.url != 'indisponível'
        ORDER BY c.id
    """

    cursor.execute(query, (recorder_guid,))
    results = cursor.fetchall()
    conn.close()

    # Retorna lista de dicionários prontos para o CameraThread
    cameras = [
        {
            "id": r[0],
            "camera_id": r[1],        # chave ajustada para compatibilidade com main.py
            "name": r[2],
            "url": r[3],
            "username": r[4],
            "password": r[5],
            "recorder_guid": r[6],
            "recorder_name": r[7],
            "stream_id": r[8]
        } for r in results
    ]
    return cameras

def start_monitoring_cameras_with_fallback(camera_recorder_list):
    cameras_raw = get_selected_cameras_with_fallback(camera_recorder_list)

    # Agrupar por câmera
    cameras_dict = {}
    for (camera_id, dguard_camera_id, camera_name, rtsp_url, username, password, recorder_guid, recorder_name, stream_id) in cameras_raw:
        key = (camera_id, recorder_guid)
        if key not in cameras_dict:
            cameras_dict[key] = {
                "camera_id": camera_id,
                "dguard_camera_id": dguard_camera_id,
                "camera_name": camera_name,
                "recorder_guid": recorder_guid,
                "recorder_name": recorder_name,
                "streams": {}
            }
        cameras_dict[key]["streams"][stream_id] = (rtsp_url, username, password)

    # Criar instâncias de CameraThread
    camera_threads = []

    for cam_data in cameras_dict.values():
        streams = cam_data["streams"]
        if 1 in streams:
            rtsp_url, username, password = streams[1]
            logger.info(f"Usando STREAM EXTRA para {cam_data['camera_name']} ({cam_data['recorder_name']})")
        elif 0 in streams:
            rtsp_url, username, password = streams[0]
            logger.info(f"Usando STREAM PRINCIPAL para {cam_data['camera_name']} ({cam_data['recorder_name']})")
        else:
            logger.warning(f"Nenhuma stream disponível para {cam_data['camera_name']} ({cam_data['recorder_name']})")
            continue

        full_rtsp_url = insert_rtsp_credentials(rtsp_url, username, password)

        cam_thread = CameraThread(full_rtsp_url,
                                  cam_data["camera_name"],
                                  cam_data["camera_id"],
                                  cam_data["dguard_camera_id"],
                                  cam_data["recorder_guid"],
                                  cam_data["recorder_name"])

        camera_threads.append(cam_thread)

    with ThreadPoolExecutor(max_workers=MAX_ACTIVE_CAMERAS) as executor:
        total_cameras = len(camera_threads)
        active_limit = min(MAX_ACTIVE_CAMERAS, total_cameras)
        queue_size = total_cameras - active_limit

        for cam_thread in camera_threads:
            logger.info(f"Iniciando thread para câmera: {cam_thread.camera_name} ({cam_thread.recorder_name})")
            executor.submit(cam_thread.start)

    return camera_threads