import threading
import time
import queue
import logging
from monitoring import start_monitoring_cameras_with_fallback

logger = logging.getLogger()  # obtém o logger raiz já configurado no monitoring.py


# Máximo de câmeras monitoradas simultaneamente
MAX_ACTIVE_CAMERAS = 100

# Fila de câmeras aguardando monitoramento
camera_queue = queue.Queue()

# Dicionário para controle das threads ativas (camera_id, recorder_guid): thread
active_threads = {}

# Lock para controle de acesso às estruturas compartilhadas
thread_lock = threading.Lock()

def add_camera_to_queue(camera_id, recorder_guid):
    """Adiciona câmera na fila para ser monitorada."""
    camera_queue.put((camera_id, recorder_guid))
    print(f"[QUEUE] Câmera adicionada à fila: ({camera_id}, {recorder_guid})")

def start_camera_thread(camera_id, recorder_guid):
    """Inicia o monitoramento de uma câmera."""
    print(f"[START] Iniciando monitoramento de câmera: ({camera_id}, {recorder_guid})")

    # Chama o método existente, ele cria a thread e inicia
    threads = start_monitoring_cameras_with_fallback([(camera_id, recorder_guid)])

    # Salva as threads no dicionário
    with thread_lock:
        for thread in threads:
            key = (camera_id, recorder_guid)
            active_threads[key] = thread

def get_active_count():
    """Retorna quantas câmeras estão sendo monitoradas ativamente."""
    with thread_lock:
        return len(active_threads)

def cleanup_finished_threads():
    """Remove do dicionário as threads que já terminaram."""
    with thread_lock:
        to_remove = []
        for key, thread in active_threads.items():
            if not thread.is_alive():
                to_remove.append(key)
        for key in to_remove:
            del active_threads[key]

def camera_manager_loop():
    previous_active_count = -1
    previous_queue_count = -1

    while True:
        cleanup_finished_threads()
        active_count = get_active_count()
        queue_count = camera_queue.qsize()

        if active_count != previous_active_count or queue_count != previous_queue_count:
            logger.info(f"[STATUS] Câmeras ativas: {active_count} / {MAX_ACTIVE_CAMERAS} | Em fila: {queue_count}")
            previous_active_count = active_count
            previous_queue_count = queue_count

        if active_count < MAX_ACTIVE_CAMERAS:
            try:
                camera_id, recorder_guid = camera_queue.get(timeout=1)
                start_camera_thread(camera_id, recorder_guid)
            except queue.Empty:
                pass
        else:
            time.sleep(0.5)

def start_camera_manager_thread():
    """Inicia a thread do gerenciador de câmeras."""
    manager_thread = threading.Thread(target=camera_manager_loop, daemon=True)
    manager_thread.start()
