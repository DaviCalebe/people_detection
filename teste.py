import json
import cv2
import sqlite3
import time
import os
from ast import literal_eval
import numpy as np

RESIZE_WIDTH = 640
RESIZE_HEIGHT = 360

def load_zones(json_path='zones.json'):
    with open(json_path, 'r') as f:
        raw = json.load(f)
        return {literal_eval(k): v for k, v in raw.items()}

def get_rtsp_from_db(camera_id, recorder_guid):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    query = """
    SELECT s.url, s.username, s.password
    FROM cameras c
    JOIN streams s ON s.camera_id = c.id AND s.stream_id = 0
    JOIN recorders r ON c.recorder_id = r.id
    WHERE c.camera_id = ? AND r.guid = ?
    """
    cursor.execute(query, (camera_id, recorder_guid))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    url, username, password = row
    if url == "indisponível":
        return None
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(url)
    netloc = f"{username}:{password}@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))

def draw_side_text_at_side(image, pt1, pt2, side):
    # ponto médio da linha
    cx = int((pt1[0] + pt2[0]) / 2)
    cy = int((pt1[1] + pt2[1]) / 2)

    dx = pt2[0] - pt1[0]
    dy = pt2[1] - pt1[1]

    length = (dx**2 + dy**2) ** 0.5
    if length == 0:
        length = 1

    # vetor perpendicular unitário
    px = -dy / length
    py = dx / length

    offset = 30

    if side == "left":
        text_x = cx + int(px * offset)
        text_y = cy + int(py * offset)
    elif side == "right":
        text_x = cx - int(px * offset)
        text_y = cy - int(py * offset)
    elif side == "top":
        vx = dx / length
        vy = dy / length
        text_x = cx - int(vx * offset)
        text_y = cy - int(vy * offset)
    elif side == "bottom":
        vx = dx / length
        vy = dy / length
        text_x = cx + int(vx * offset)
        text_y = cy + int(vy * offset)
    else:
        # centralizado se side inválido
        text_x = cx
        text_y = cy

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.7
    thickness = 2

    (text_width, text_height), baseline = cv2.getTextSize(side, font, font_scale, thickness)

    text_x -= text_width // 2
    text_y += text_height // 2

    # fundo preto para melhor leitura
    cv2.rectangle(image,
                  (text_x - 5, text_y + baseline - text_height - 5),
                  (text_x + text_width + 5, text_y + baseline + 5),
                  (0, 0, 0),
                  thickness=cv2.FILLED)

    cv2.putText(image, side, (text_x, text_y), font, font_scale, (0, 255, 0), thickness)

def main():
    camera_id = int(input("Digite o camera_id: ").strip())
    recorder_guid = input("Digite o recorder_guid: ").strip()
    key = (camera_id, recorder_guid)
    json_path = 'zones.json'

    zones = load_zones(json_path)
    last_mtime = os.path.getmtime(json_path)

    rtsp_url = get_rtsp_from_db(camera_id, recorder_guid)
    if not rtsp_url:
        print("URL RTSP não encontrada ou inválida.")
        return

    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        print("Erro ao abrir o vídeo")
        return

    print("Pressione 'q' para sair")

    while True:
        try:
            mtime = os.path.getmtime(json_path)
            if mtime != last_mtime:
                zones = load_zones(json_path)
                last_mtime = mtime
                print(f"zones.json atualizado e recarregado em {time.strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"Erro ao recarregar zones.json: {e}")

        if key not in zones:
            print(f"Configuração não encontrada para {key} no zones.json")
            zone = None
        else:
            zone = zones[key]

        ret, frame = cap.read()
        if not ret:
            print("Erro na captura do frame")
            break

        resized = cv2.resize(frame, (RESIZE_WIDTH, RESIZE_HEIGHT))

        if zone:
            if zone["type"] == "side":
                pt1, pt2 = zone["line"]
                cv2.line(resized, pt1, pt2, (0, 255, 0), 2)
                draw_side_text_at_side(resized, pt1, pt2, zone.get("side", ""))
            elif zone["type"] == "area":
                polygon = zone["polygon"]
                cv2.polylines(resized, [np.array(polygon, dtype=np.int32)], isClosed=True, color=(0, 0, 255), thickness=2)

        cv2.imshow("Visualização da Zona", resized)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
