import threading
from monitoring import start_monitoring_cameras

# Para controlar threads abertas e evitar conflitos, vamos guardar as threads ativas
active_threads = []

async def handle_set_cameras(camera_id: int, recorder_guid: str):
    # Pode ser uma lista para futuras expansões
    cameras_to_start = [(camera_id, recorder_guid)]

    # Iniciar monitoramento das câmeras recebidas
    threads = start_monitoring_cameras(cameras_to_start)

    # Guardar as threads ativas para controle futuro, caso queira parar depois
    active_threads.extend(threads)

    return {"message": "Monitoramento iniciado para a(s) câmera(s)", "cameras": cameras_to_start}
