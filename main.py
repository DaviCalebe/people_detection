import time
import logging
from monitoring import CameraThread, insert_rtsp_credentials, get_recorders, get_cameras_by_recorder

# --- Configurar logger básico para o main
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Tempo que cada gravador terá suas câmeras abertas
RUN_TIME_PER_RECORDER = 10  # segundos

def ronda_virtual(modo="first"):
    """
    Executa a ronda virtual percorrendo todos os gravadores.
    
    :param modo: Define como abrir as câmeras de cada gravador.
                 Valores possíveis:
                   - "first": abre apenas a first câmera do gravador (default).
                   - "all": abre all as câmeras do gravador em paralelo.
    """
    while True:
        recorders = get_recorders()
        for recorder in recorders:
            cameras = get_cameras_by_recorder(recorder["guid"])
            if not cameras:
                logger.warning(f"Gravador {recorder['name']} não possui câmeras.")
                continue

            logger.info(f"Iniciando gravador {recorder['name']} com {len(cameras)} câmeras.")

            if modo == "all":
                # ============================================================
                # OPÇÃO 1 - Rodar all as câmeras do gravador
                # ============================================================
                threads = []
                for cam in cameras:
                    full_rtsp = insert_rtsp_credentials(cam["url"], cam["username"], cam["password"])

                    t = CameraThread(
                        rtsp_url=full_rtsp,
                        camera_name=cam["name"],
                        camera_id=cam["id"],
                        dguard_camera_id=cam["camera_id"],
                        recorder_guid=recorder["guid"],
                        recorder_name=recorder["name"]
                    )
                    t.start()
                    threads.append(t)

                # Mantém all as câmeras rodando pelo tempo definido
                time.sleep(RUN_TIME_PER_RECORDER)

                # Para all as câmeras
                for t in threads:
                    t.stop()
                    t.join()

            else:
                # ============================================================
                # OPÇÃO 2 - Rodar apenas a first câmera do gravador
                # ============================================================
                cam = cameras[0]  # pega apenas a first câmera
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
                t.start()

                time.sleep(RUN_TIME_PER_RECORDER)

                t.stop()
                t.join()

            logger.info(f"Finalizado gravador {recorder['name']}.\n")



if __name__ == "__main__":
    try:
        logger.info("Iniciando ronda virtual...")
        ronda_virtual()
    except KeyboardInterrupt:
        logger.info("Ronda virtual interrompida manualmente.")
