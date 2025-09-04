import sqlite3
import subprocess
import threading
import time
import cv2
import json
import os
import logging
import torch
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
logger.setLevel(logging.DEBUG)

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

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Usando dispositivo: {device}")
model = YOLO('models/yolov8n.pt')
model.to(device)

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
    """
    Tenta obter a resolução da stream extra (subtype=1). 
    Se demorar >10s ou der erro, troca para subtype=0 (stream principal) e tenta novamente.
    Logs detalhados indicam cada tentativa.
    """
    urls_to_try = [rtsp_url, rtsp_url.replace("subtype=1", "subtype=0")]

    for idx, url in enumerate(urls_to_try):
        stream_type = "extra" if idx == 0 else "principal"

        if idx == 1:
            logger.info(f"[{camera_name} - {recorder_name}] Tentando fallback para stream principal...")

        try:
            logger.debug(f"[{camera_name} - {recorder_name}] Tentando ffprobe na stream {stream_type}: {url}")
            start_time = time.time()

            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-rtsp_transport", "tcp",
                    "-timeout", "10000000",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height",
                    "-of", "json",
                    url
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10
            )

            end_time = time.time()
            logger.debug(f"[{camera_name} - {recorder_name}] ffprobe {stream_type} concluído em {end_time - start_time:.2f}s")

            if result.returncode != 0:
                logger.warning(f"[{camera_name} - {recorder_name}] Erro ffprobe na stream {stream_type}: {result.stderr.strip()}")
                continue

            info = json.loads(result.stdout)
            width = info["streams"][0]["width"]
            height = info["streams"][0]["height"]
            logger.debug(f"[{camera_name} - {recorder_name}] Resolução obtida ({stream_type}): {width}x{height}")
            return width, height

        except subprocess.TimeoutExpired:
            logger.warning(f"[{camera_name} - {recorder_name}] ffprobe timeout de 10s na stream {stream_type}")
        except Exception as e:
            logger.error(f"[{camera_name} - {recorder_name}] Erro inesperado ffprobe na stream {stream_type}: {e}")

    logger.error(f"[{camera_name} - {recorder_name}] Não foi possível obter resolução de nenhuma stream")
    return None


class FreshestFFmpegFrame(threading.Thread):
    def __init__(self, ffmpeg_proc, width, height, timeout=5):
        super().__init__()
        self.proc = ffmpeg_proc
        self.width = width
        self.height = height
        self.frame = None
        self.lock = threading.Lock()
        self.running = True
        self.last_frame_time = time.time()
        self.timeout = timeout  # máximo tempo sem frame
        self.start()

    def run(self):
        frame_size = self.width * self.height * 3
        while self.running:
            try:
                raw_frame = self.proc.stdout.read(frame_size)
                
                if not raw_frame:
                    # se passar do timeout sem frame, sai do loop
                    if time.time() - self.last_frame_time > self.timeout:
                        logging.warning(f"FFmpeg não retornou frame por mais de {self.timeout}s")
                        break
                    time.sleep(0.01)  # evita busy loop
                    continue

                if len(raw_frame) != frame_size:
                    continue  # frame incompleto

                frame = np.frombuffer(raw_frame, np.uint8).reshape((self.height, self.width, 3))
                with self.lock:
                    self.frame = frame
                    self.last_frame_time = time.time()  # atualiza o relógio do último frame

            except Exception as e:
                logging.error(f"Erro lendo frame FFmpeg: {e}")
                break

    def read(self):
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    def stop(self):
        self.running = False
        self.join()  # join normal, sem timeout

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
        self.error_thread_running = False  # flag nova para encerrar thread de erros

    def trigger_error_event(self, reason):
        if not self.error_event_sent:
            logger.warning(f"[{self.camera_name} - {self.recorder_name}] Acionando evento por erro: {reason}")
            # dispara em thread separada para não travar
            threading.Thread(
                target=set_event_schedule,
                args=(self.dguard_camera_id, self.recorder_guid),
                daemon=True
            ).start()
            self.error_event_sent = True

    def stop(self):
        self.running = False

        # parar freshest
        if self.freshest:
            self.freshest.stop()

        # parar thread de erros
        self.error_thread_running = False
        if self.error_thread and self.error_thread.is_alive():
            self.error_thread.join(timeout=1)

        # fechar FFmpeg de forma segura
        if self.ffmpeg_proc and self.ffmpeg_proc.poll() is None:
            try:
                self.ffmpeg_proc.terminate()
                for _ in range(50):  # até 5s
                    if self.ffmpeg_proc.poll() is not None:
                        break
                    time.sleep(0.1)
                else:
                    self.ffmpeg_proc.kill()
            except Exception:
                self.ffmpeg_proc.kill()

        if SHOW_VIDEO:
            try:
                cv2.destroyWindow(f"{self.camera_name}")
            except:
                pass

        logger.info(f"[{self.camera_name} - {self.recorder_name}] CameraThread finalizada com sucesso.")

    def _log_ffmpeg_errors(self, stderr_pipe):
        self.error_thread_running = True
        pps_error_detected = False
        ref_error_detected = False
        disconnect_error_detected = False

        while self.error_thread_running:
            line = stderr_pipe.readline()
            if not line:
                break
            decoded_line = line.decode('utf-8', errors='ignore').strip()

            if "non-existing PPS" in decoded_line:
                if not pps_error_detected:
                    logger.error(f"{self.camera_name} ({self.recorder_name}): PPS ausente no stream RTSP.")
                    pps_error_detected = True
                continue

            if pps_error_detected and any(x in decoded_line for x in [
                "decode_slice_header error", "no frame!", "Error submitting packet", "Invalid data found"
            ]):
                continue

            if "reference picture missing" in decoded_line or "Missing reference picture" in decoded_line:
                if not ref_error_detected:
                    logger.error(f"{self.camera_name} ({self.recorder_name}): Referência de frame ausente.")
                    ref_error_detected = True
                continue

            if ref_error_detected and any(x in decoded_line for x in [
                "decode_slice_header error", "bytestream", "Missing reference picture",
                "no frame!", "Invalid data found"
            ]):
                continue

            if "Error number -10054" in decoded_line:
                if not disconnect_error_detected:
                    logger.error(f"{self.camera_name} ({self.recorder_name}): Desconexão remota detectada (-10054).")
                    disconnect_error_detected = True
                    self.trigger_error_event("Desconexão remota detectada (-10054)")
                continue

            logger.error(f"{self.camera_name} ({self.recorder_name}) {decoded_line}")
            self.trigger_error_event("Erro detectado no FFmpeg")

    def run(self):
        thread_start_time = time.time()
        logger.debug(f"[{self.camera_name} - {self.recorder_name}] Iniciando monitoramento da câmera")

        # resolução RTSP
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

        # iniciar ffmpeg
        ffmpeg_start = time.time()
        self.ffmpeg_proc = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=4096,
            text=False
        )
        logger.debug(f"[{self.camera_name} - {self.recorder_name}] FFmpeg iniciado em {time.time() - ffmpeg_start:.2f}s")

        if self.ffmpeg_proc.stdout is None or self.ffmpeg_proc.stderr is None:
            self.trigger_error_event("FFmpeg não iniciou corretamente")
            return

        self.freshest = FreshestFFmpegFrame(self.ffmpeg_proc, width, height, timeout=20)

        # aguardar primeiro frame
        first_frame_time = time.time()
        frame = None
        while frame is None and self.running:
            frame = self.freshest.read()
            if frame is None:
                time.sleep(0.05)
        logger.debug(f"[{self.camera_name} - {self.recorder_name}] Primeiro frame após {time.time() - first_frame_time:.2f}s")

        # iniciar thread de erros
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

                # processamento do modelo
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
                        self.trigger_error_event("Pessoa detectada")
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
            logger.debug(f"[{self.camera_name} - {self.recorder_name}] Monitoramento encerrado após {time.time() - thread_start_time:.2f}s")
            self.stop()


def get_recorders():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, guid, name FROM recorders")
    recorders = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "guid": r[1], "name": r[2]} for r in recorders]


def get_recorders_server1():
    """
    Retorna todos os gravadores que pertencem ao Server 1.
    """
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, guid, name FROM recorders WHERE server_id = 1")
    recorders = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "guid": r[1], "name": r[2]} for r in recorders]


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
            c.camera_id,
            c.name,
            s.url,
            s.username,
            s.password,
            r.guid AS recorder_guid,
            r.name AS recorder_name,
            s.stream_id
        FROM cameras c
        JOIN streams s ON s.camera_id = c.id AND s.stream_id = 1
        JOIN recorders r ON c.recorder_id = r.id
        WHERE r.guid = ? 
        AND s.url != 'indisponível'
        AND c.active = 1   -- câmeras ativas
        ORDER BY c.id;
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