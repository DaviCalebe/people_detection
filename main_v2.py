import time
import cv2
import subprocess
import numpy as np
import json
import threading
import argparse
from ultralytics import YOLO
from events.scheduler import set_event_schedule

# Configurações globais
CONFIDENCE_THRESHOLD = 0.5
RESIZE_WIDTH = 640
RESIZE_HEIGHT = 360
PROCESS_EVERY = 5
event_delay = 30  # segundos entre eventos

# YOLOv8 modelo leve
model = YOLO('models/yolov8n.pt')

# Carregar dados do inventário
with open('merged_inventory.json', 'r', encoding='utf-8') as f:
    servers_data = json.load(f)

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

def select_stream0(camera_data):
    for stream in camera_data['streams']:
        if stream.get('streamId') == 0:
            url = stream['remoteUrl']['url']
            if url and url.lower() != 'indisponível':
                return url
    return None

def main():
    args = parse_arguments()
    selected_cameras = []

    if args.server:
        for server_name, server_data in servers_data['servers'].items():
            if server_name == args.server:
                for recorder_name, recorder_data in server_data['recorders'].items():
                    for camera_name, camera_data in recorder_data['cameras'].items():
                        url = select_stream0(camera_data)
                        if url:
                            selected_cameras.append((camera_name, url))

    elif args.recorder:
        for server_data in servers_data['servers'].values():
            for recorder_name, recorder_data in server_data['recorders'].items():
                if recorder_name in args.recorder:
                    for camera_name, camera_data in recorder_data['cameras'].items():
                        url = select_stream0(camera_data)
                        if url:
                            selected_cameras.append((camera_name, url))

    elif args.camera:
        for server_data in servers_data['servers'].values():
            for recorder_data in server_data['recorders'].values():
                for camera_name, camera_data in recorder_data['cameras'].items():
                    if camera_name in args.camera:
                        url = select_stream0(camera_data)
                        if url:
                            selected_cameras.append((camera_name, url))

    else:
        print("Nenhum argumento fornecido. Selecione manualmente:")
        servers = list(servers_data['servers'].keys())
        for i, server in enumerate(servers):
            print(f"{i + 1}: {server}")
        server_idx = int(input("Escolha o servidor: ")) - 1
        selected_server = servers[server_idx]

        recorders = list(servers_data['servers'][selected_server]['recorders'].keys())
        for i, recorder in enumerate(recorders):
            print(f"{i + 1}: {recorder}")
        recorder_idx = int(input("Escolha o gravador: ")) - 1
        selected_recorder = recorders[recorder_idx]

        cameras = list(servers_data['servers'][selected_server]['recorders'][selected_recorder]['cameras'].keys())
        for i, camera in enumerate(cameras):
            print(f"{i + 1}: {camera}")
        selected_idxs = input("Escolha as câmeras (ex: 1 2 3): ").split()
        for idx in selected_idxs:
            camera_name = cameras[int(idx) - 1]
            camera_data = servers_data['servers'][selected_server]['recorders'][selected_recorder]['cameras'][camera_name]
            url = select_stream0(camera_data)
            if url:
                selected_cameras.append((camera_name, url))

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
