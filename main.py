import time
from monitoring import CameraThread, insert_rtsp_credentials, get_recorders, get_cameras_by_recorder_virtual
import logging

# --- Configurar logger básico para o main
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Tempo que cada gravador terá suas câmeras abertas
RUN_TIME_PER_RECORDER = 10  # segundos

def ronda_virtual():
    """
    Executa a ronda virtual percorrendo todos os gravadores.
    Para cada gravador, abre todas as suas câmeras por RUN_TIME_PER_RECORDER segundos.
    """
    while True:
        recorders = get_recorders()
        for recorder in recorders:
            cameras = get_cameras_by_recorder_virtual(recorder["guid"])
            if not cameras:
                logger.warning(f"Gravador {recorder['name']} não possui câmeras disponíveis.")
                continue

            logger.info(f"Iniciando gravador {recorder['name']} com {len(cameras)} câmeras.")

            threads = []

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

            # Mantém todas as câmeras rodando por RUN_TIME_PER_RECORDER segundos

            # Para todas as câmeras do gravador
            for t in threads:
                t.stop()
                t.join()

            logger.info(f"Finalizado gravador {recorder['name']}.\n")


if __name__ == "__main__":
    try:
        logger.info("Iniciando ronda virtual...")
        ronda_virtual()
    except KeyboardInterrupt:
        logger.info("Ronda virtual interrompida manualmente.")
