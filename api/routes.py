from fastapi import APIRouter
from pydantic import BaseModel
from api.controller import handle_set_cameras

router = APIRouter()


class CameraRequest(BaseModel):
    camera_id: int
    recorder_guid: str


@router.post("/set-cameras")
async def set_cameras(request: CameraRequest):
    # Passa para o controller que executa o monitoramento
    print(f"Recebido: camera_id={request.camera_id}, recorder_guid={request.recorder_guid}")

    return await handle_set_cameras(request.camera_id, request.recorder_guid)
