## Como configurar o ambiente virtual

1. Crie o ambiente virtual:

   ```bash
   python -m venv .venv

2. Ative o ambiente:

   ```bash
   source .venv/Scripts/activate

3. Instale as dependências:

   ```bash
   pip install -r requirements.txt

4. Outras dependências (precisam ser instaladas via terminal):
   
   ```bash
   winget install ffmpeg

5. Caso queira rodar o YOLO pela GPU(opcional):
   ```bash
   pip install torch==2.7.0+cu118 torchvision==0.15.1+cu118 torchaudio==2.0.1 --index-url https://download.pytorch.org/whl/cu118

## Comando para iniciar o servidor
   
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000

## Exemplo de requisição POST para API

   ```bash
   curl -X POST "http://localhost:8000/set-cameras" -H "Content-Type: application/json" -d "{\"camera_id\":13,\"recorder_guid\":\"{B54AE1B4-CCB8-4D80-9E85-4A7593FF789C}\"}"