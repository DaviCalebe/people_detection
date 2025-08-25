import time
import logging
from monitoring import CameraThread, insert_rtsp_credentials, get_recorders, get_cameras_by_recorder

# --- Configurar logger básico para o main
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Tempo que cada gravador terá suas câmeras abertas (em segundos)
RUN_TIME_PER_RECORDER = 10

def ronda_virtual(selected_recorders_names=None):
    """
    Executa a ronda virtual percorrendo os gravadores selecionados.
    Se selected_recorders_names for None, percorre todos.
    """
    recorders = get_recorders()

    # Filtrar gravadores apenas pelos nomes selecionados, se houver
    if selected_recorders_names:
        recorders = [r for r in recorders if r["name"] in selected_recorders_names]

    if not recorders:
        logger.warning("Nenhum gravador encontrado para a ronda.")
        return

    for recorder in recorders:
        cameras = get_cameras_by_recorder(recorder["guid"])
        if not cameras:
            logger.warning(f"Não há câmeras no gravador {recorder['name']}")
            continue

        logger.info(f"Iniciando gravador {recorder['name']} com {len(cameras)} câmeras.")

        threads = []
        for cam in cameras:
            # montar RTSP completo com credenciais
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

        # esperar RUN_TIME_PER_RECORDER segundos antes de parar todas as câmeras do gravador
        time.sleep(RUN_TIME_PER_RECORDER)
        for t in threads:
            t.stop()
            t.join()

        logger.info(f"Gravador {recorder['name']} finalizado.")

if __name__ == "__main__":
    # Lista com os nomes dos gravadores que você quer testar
    test_recorders = [
        "PE_MATRIZ_DVR_1",
        "PE_MATRIZ_DVR_2",
        "MATRIZ_NVR_4",
        "MATRIZ_NVR_5",
        "MATRIZ_NVR_6"
        "PE_BOA_VIAGEM_CENTER_8_ANDAR",
        "PE_BOA_VIAGEM_CENTER_11_ANDAR"
    ]

    ronda_virtual(selected_recorders_names=test_recorders)
