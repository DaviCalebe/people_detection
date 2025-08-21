import time
import logging
from monitoring import CameraThread, insert_rtsp_credentials, get_recorders, get_cameras_by_recorder

# --- Configurar logger básico para o main
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Tempo que cada gravador terá sua câmera aberta
RUN_TIME_PER_RECORDER = 10  # segundos

def ronda_virtual():
    """
    Executa a ronda virtual percorrendo todos os gravadores.
    Para cada gravador, abre apenas a primeira câmera por RUN_TIME_PER_RECORDER segundos.
    """
    while True:
        recorders = get_recorders()
        for recorder in recorders:
            cameras = get_cameras_by_recorder(recorder["guid"])
            if not cameras:
                logger.warning(f"Gravador {recorder['name']} não possui câmeras.")
                continue

                        # Inicia todas as câmeras do gravador
            for cam in cameras:
                full_rtsp = insert_rtsp_credentials(cam["url"], cam["username"], cam["password"])

                t = CameraThread(
                    rtsp_url=full_rtsp,
                    camera_name=cam["name"],
                    camera_id=cam["id"],
                    dguard_camera_id=cam["dguard_camera_id"],
                    recorder_guid=cam["recorder_guid"],
                    recorder_name=cam["recorder_name"]
                )
                t.start()
                threads.append(t)

"""             cam = cameras[0]  # pega apenas a primeira câmera
            full_rtsp = insert_rtsp_credentials(cam["url"], cam["username"], cam["password"])

            logger.info(f"Iniciando gravador {recorder['name']} com a câmera {cam['name']}.")

            t = CameraThread(
                rtsp_url=full_rtsp,
                camera_name=cam["name"],
                camera_id=cam["id"],
                dguard_camera_id=cam["camera_id"],
                recorder_guid=recorder["guid"],
                recorder_name=recorder["name"]
            )
            t.start() """
            time.sleep(RUN_TIME_PER_RECORDER)
            t.running = False
            t.join()

            logger.info(f"Finalizado gravador {recorder['name']}.\n")

if __name__ == "__main__":
    try:
        logger.info("Iniciando ronda virtual...")
        ronda_virtual()
    except KeyboardInterrupt:
        logger.info("Ronda virtual interrompida manualmente.")
