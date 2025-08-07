from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from api.routes import router as api_router
import uvicorn
import logging

# Logger padrão do Uvicorn
logger = logging.getLogger("uvicorn.error")

app = FastAPI()

# Handler global para erros de validação (422)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    try:
        body = await request.json()
    except Exception:
        body = "Não foi possível decodificar o JSON enviado"

    logger.error("Erro 422 - Validação falhou:\nErros: %s\nDados enviados: %s", exc.errors(), body)

    return JSONResponse(
        status_code=422,
        content={
            "message": "Erro de validação nos dados enviados",
            "errors": exc.errors(),
            "dados_enviados": body
        },
    )

# Inclui as rotas da API
app.include_router(api_router)

# Execução local
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
