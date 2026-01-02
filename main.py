import sqlite3
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
    """
    TIMEOUT_PER_RECORDER = 60  # segundos

    while True:
        recorders = get_recorders()

        # filtrar apenas gravadores selecionados
        if selected_recorders_names:
            recorders = [r for r in recorders if r["name"] in selected_recorders_names]

        if not recorders:
            logger.warning("Nenhum gravador encontrado para a ronda.")
            return

        total = len(recorders)
        for idx, recorder in enumerate(recorders, start=1):
            logger.info(f"[{idx}/{total}] Iniciando gravador {recorder['name']}")

            cameras = get_cameras_by_recorder_virtual(recorder["guid"])
            if not cameras:
                logger.warning(f"[{idx}/{total}] Gravador {recorder['name']} não possui câmeras.")
                continue

            threads = []
            start_time = time.time()

            if modo == "all":
                # cria uma thread por câmera
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

            else:  # modo "first"
                cam = cameras[0]
                full_rtsp = insert_rtsp_credentials(cam["url"], cam["username"], cam["password"])
                logger.info(f"[{idx}/{total}] Iniciando câmera {cam['name']} do gravador {recorder['name']}")
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

            # --- Monitorar até timeout ou todas finalizarem ---
            while True:
                elapsed = time.time() - start_time

                if elapsed > TIMEOUT_PER_RECORDER:
                    logger.error(f"[{idx}/{total}] Tempo limite de {TIMEOUT_PER_RECORDER}s atingido no gravador {recorder['name']}. Encerrando forçadamente.")
                    for t in threads:
                        t.stop()
                        if t.is_alive():
                            t.join(timeout=1)
                    break

                # Se todas terminaram antes do timeout, sai
                if all(not t.is_alive() for t in threads):
                    break

                time.sleep(1)

            logger.info(f"[{idx}/{total}] Finalizado gravador {recorder['name']}.\n")


if __name__ == "__main__":
    # Lista com os nomes dos gravadores que você quer testar
    test_recorders = [
        "AC_RIO_BRANCO",
    ]

    try:
        logger.info("Iniciando ronda virtual...")

        # Pegar todos os gravadores do Server 1
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM recorders WHERE server_id = 1")
        server1_recorders = [r[0] for r in cursor.fetchall()]
        conn.close()

        ronda_virtual(selected_recorders_names=test_recorders, modo="all")

    except KeyboardInterrupt:
        logger.info("Ronda virtual interrompida manualmente.")