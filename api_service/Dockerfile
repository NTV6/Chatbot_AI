FROM python:3.11

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r api_service/requirements.txt

CMD ["uvicorn", "api_service.main:app", "--host", "0.0.0.0", "--port", "8000"]