FROM python:3.11

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt || pip install --no-cache-dir chromadb

CMD ["uvicorn", "rag:app", "--host", "0.0.0.0", "--port", "9000"]
