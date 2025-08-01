from fastapi import APIRouter
from pydantic import BaseModel
from api.camera_manager import add_camera_to_queue  # <-- importar a função correta

router = APIRouter()

class CameraRequest(BaseModel):
    camera_id: int
    recorder_guid: str

@router.post("/set-cameras")
async def set_cameras(request: CameraRequest):
    # Adiciona na fila de monitoramento (com controle de 100 simultâneas)
    add_camera_to_queue(request.camera_id, request.recorder_guid)
    return {
        "message": f"Câmera {request.camera_id} ({request.recorder_guid}) adicionada à fila."
    }
