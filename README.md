## Como configurar o ambiente virtual

1. Crie o ambiente virtual:

   ```bash
   python -m venv .venv

2. Ative o ambiente:

   ```bash
   .\.venv\Scripts\activate

3. Instale as dependências:

   ```bash
   pip install -r requirements.txt


## Comando para iniciar o servidor
   
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000