from fastapi import FastAPI
from api.routes import router as api_router
from api.camera_manager import start_camera_manager_thread
import uvicorn

app = FastAPI()

# Roda a thread do manager no startup
@app.on_event("startup")
async def startup_event():
    start_camera_manager_thread()

app.include_router(api_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
