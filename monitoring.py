import sqlite3
import subprocess
import threading
import time
import cv2
import json
import os
import logging
import platform
import concurrent.futures
import psutil
import numpy as np
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

# Substituir print por logging.info (ou warning/error etc)
print = logger.info  # Redireciona todos os print() para logging.info()

SHOW_VIDEO = False
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

def get_max_workers():
    try:
        if platform.system() != "Windows":
            import resource
            soft_limit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
            return max(1, soft_limit - 100)
        else:
            return 32
    except:
        return 32

MAX_WORKERS = get_max_workers()

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
        self.error_event_sent = False

    def trigger_error_event(self, reason):
        if not self.error_event_sent:
            logger.warning(f"[{self.camera_name} - {self.recorder_name}] Acionando evento por erro: {reason}")
            set_event_schedule(self.dguard_camera_id, self.recorder_guid)
            self.error_event_sent = True

    def run(self):
        resolution = get_rtsp_resolution(self.rtsp_url, self.camera_name, self.recorder_name)
        if not resolution:
            self.trigger_error_event("Falha ao obter resolução RTSP")
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

        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=4096,
            text=False
        )

        if proc.stdout is None or proc.stderr is None:
            self.trigger_error_event("FFmpeg não iniciou corretamente")
            return

        freshest = FreshestFFmpegFrame(proc, width, height)

        def log_ffmpeg_errors(stderr_pipe, camera_name, recorder_name, dguard_camera_id, recorder_guid):
            pps_error_detected = False
            ref_error_detected = False
            disconnect_error_detected = False

            for line in iter(stderr_pipe.readline, b''):
                decoded_line = line.decode('utf-8', errors='ignore').strip()

                # Tratamento PPS ausente
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

                # Tratamento referência de frame ausente
                if "reference picture missing" in decoded_line or "Missing reference picture" in decoded_line:
                    if not ref_error_detected:
                        logger.error(f"{camera_name} ({recorder_name}): Referência de frame ausente. Ignorando mensagens repetidas.")
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

                # Tratamento específico para desconexão remota -10054
                if "Error number -10054" in decoded_line:
                    if not disconnect_error_detected:
                        logger.error(f"{camera_name} ({recorder_name}): Desconexão remota detectada (Error number -10054).")
                        disconnect_error_detected = True
                        set_event_schedule(dguard_camera_id, recorder_guid)
                    continue

                # Log geral para outras mensagens de erro e acionamento de evento
                logger.error(f"{camera_name} ({recorder_name}) {decoded_line}")
                set_event_schedule(dguard_camera_id, recorder_guid)

        error_thread = threading.Thread(
            target=log_ffmpeg_errors,
            args=(proc.stderr, self.camera_name, self.recorder_name, self.dguard_camera_id, self.recorder_guid),
            daemon=True
        )
        error_thread.start()

        try:
            frame_count = 0
            last_sent = 0
            person_detected = False
            last_total_detections = 0

            # no_frame_start = time.time()
            # start_time = None
            thread_start_time = time.time()

            while self.running and (time.time() - thread_start_time < 20):
                frame = freshest.read()

                if frame is None:
                    continue
                # if frame is None:
                #     if time.time() - no_frame_start > 10:
                #         self.trigger_error_event("Sem frames válidos por 10s")
                #         break
                #     continue
                # else:
                #     if start_time is None:
                #         start_time = time.time()
                #     no_frame_start = time.time()

                # if time.time() - start_time > 5:
                #     break

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

                if total_detections != last_total_detections:
                    last_total_detections = total_detections

                if person_detected:
                    current_time = time.time()
                    if current_time - last_sent >= event_delay:
                        print(f"[WARNING] Pessoa detectada! ({self.camera_name} - {self.recorder_name})")
                        set_event_schedule(self.dguard_camera_id, self.recorder_guid)
                        last_sent = current_time
                    break

                if SHOW_VIDEO:
                    cv2.imshow(f'{self.camera_name}', resized)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

            if person_detected:
                print(f"DETECÇÃO REALIZADA para {self.camera_name} ({self.recorder_name})")
            else:
                print(f"NENHUMA DETECÇÃO para {self.camera_name} ({self.recorder_name})")

        except Exception as e:
            logger.exception(f"Erro inesperado em {self.camera_name} ({self.recorder_name}): {e}")
            self.trigger_error_event("Erro inesperado na thread da câmera")

        finally:
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


def get_selected_cameras_with_fallback(camera_recorder_list):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if not camera_recorder_list:
        return []

    or_clauses = []
    params = []
    for cam_id, rec_guid in camera_recorder_list:
        or_clauses.append("(c.camera_id = ? AND r.guid = ?)")
        params.extend([cam_id, rec_guid])

    # Buscar streams de ambas as IDs (0 e 1), e ordenar para termos sempre principal e extra
    query = f"""
        SELECT
            c.id,
            c.camera_id AS dguard_camera_id,
            c.name,
            s.url,
            s.username,
            s.password,
            r.guid,
            r.name AS recorder_name,
            s.stream_id
        FROM cameras c
        JOIN streams s ON s.camera_id = c.id AND s.stream_id IN (0,1)
        JOIN recorders r ON c.recorder_id = r.id
        WHERE {" OR ".join(or_clauses)} AND s.url != 'indisponível'
        ORDER BY c.id, s.stream_id DESC  -- Ordena para priorizar stream extra (1) antes da principal (0)
    """

    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    return results


def start_monitoring_cameras(camera_recorder_list):
    cameras = get_selected_cameras(camera_recorder_list)
    threads = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for (camera_id, dguard_camera_id, camera_name, rtsp_url, username, password, recorder_guid, recorder_name) in cameras:
            full_rtsp_url = insert_rtsp_credentials(rtsp_url, username, password)
            cam_thread = CameraThread(full_rtsp_url, camera_name, camera_id, dguard_camera_id, recorder_guid, recorder_name)
            print(f"Iniciando thread para câmera: {camera_name} ({recorder_name})")
            futures.append(executor.submit(cam_thread.start))
            threads.append(cam_thread)

    print(f"MAX_WORKERS usado: {MAX_WORKERS}")
    return threads


def start_monitoring_cameras_with_fallback(camera_recorder_list):
    cameras_raw = get_selected_cameras_with_fallback(camera_recorder_list)
    threads = []
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

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for cam_key, cam_data in cameras_dict.items():
            streams = cam_data["streams"]
            if 1 in streams:
                rtsp_url, username, password = streams[1]
                print(f"Usando STREAM EXTRA para {cam_data['camera_name']} ({cam_data['recorder_name']})")
            elif 0 in streams:
                rtsp_url, username, password = streams[0]
                print(f"Usando STREAM PRINCIPAL para {cam_data['camera_name']} ({cam_data['recorder_name']})")
            else:
                print(f"Nenhuma stream disponível para {cam_data['camera_name']} ({cam_data['recorder_name']})")
                continue

            full_rtsp_url = insert_rtsp_credentials(rtsp_url, username, password)

            cam_thread = CameraThread(full_rtsp_url,
                                      cam_data["camera_name"],
                                      cam_data["camera_id"],
                                      cam_data["dguard_camera_id"],
                                      cam_data["recorder_guid"],
                                      cam_data["recorder_name"])
            futures.append(executor.submit(cam_thread.start))
            threads.append(cam_thread)

    print(f"MAX_WORKERS usado: {MAX_WORKERS}")
    return threads

def monitorar_processo_periodicamente(intervalo_minutos=0.1):
    import os

    def monitor():
        process = psutil.Process(os.getpid())
        while True:
            handles = process.num_handles() if hasattr(process, 'num_handles') else "N/A"
            open_files = process.open_files()
            num_threads = process.num_threads()
            children = process.children()

            logger.info(f"[MONITORAMENTO] Handles: {handles}, Threads: {num_threads}, "
                        f"Subprocessos filhos: {len(children)}, Arquivos abertos: {len(open_files)}")
            time.sleep(intervalo_minutos * 60)

    t = threading.Thread(target=monitor, daemon=True)
    t.start()

monitorar_processo_periodicamente()
