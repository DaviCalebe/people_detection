import time
import logging
from monitoring import CameraThread, insert_rtsp_credentials, get_recorders, get_cameras_by_recorder_virtual

# --- Configurar logger básico
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Tempo que cada gravador terá suas câmeras abertas (em segundos)
RUN_TIME_PER_RECORDER = 10

def ronda_virtual(selected_recorders_names=None, modo="first"):
    """
    Executa a ronda virtual percorrendo os gravadores selecionados.

    :param selected_recorders_names: lista com nomes dos gravadores a rodar.
                                     Se None, roda todos.
    :param modo: Define como abrir as câmeras de cada gravador.
                 "first" = abre apenas a primeira câmera
                 "all"   = abre todas as câmeras
    """
    while True:
        recorders = get_recorders()

        # filtrar apenas gravadores selecionados
        if selected_recorders_names:
            recorders = [r for r in recorders if r["name"] in selected_recorders_names]

        if not recorders:
            logger.warning("Nenhum gravador encontrado para a ronda.")
            return

        for recorder in recorders:
            cameras = get_cameras_by_recorder_virtual(recorder["guid"])
            if not cameras:
                logger.warning(f"Gravador {recorder['name']} não possui câmeras.")
                continue

            logger.info(f"Iniciando gravador {recorder['name']} com {len(cameras)} câmeras.")

            if modo == "all":
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

                time.sleep(RUN_TIME_PER_RECORDER)

                for t in threads:
                    t.join()

            else:  # modo "first"
                cam = cameras[0]
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
                t.join()

            logger.info(f"Finalizado gravador {recorder['name']}.\n")


if __name__ == "__main__":
    # Lista com os nomes dos gravadores que você quer testar
    test_recorders = [
        "BA_LUIS_EDUARDO_MAGALHAES",

    ]


    try:
        logger.info("Iniciando ronda virtual...")

        # Pegar todos os gravadores do Server 1
        import sqlite3
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM recorders WHERE server_id = 1")
        server1_recorders = [r[0] for r in cursor.fetchall()]
        conn.close()

        ronda_virtual(selected_recorders_names=test_recorders, modo="all")

    except KeyboardInterrupt:
        logger.info("Ronda virtual interrompida manualmente.")