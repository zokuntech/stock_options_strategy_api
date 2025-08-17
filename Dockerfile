aws ecs describe-services --cluster stock-options-strategy-api-prod --services stock-options-strategy-api-prod --query "services[0].taskDefinition" --output textFROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything in the repo (including app.py and utils/)
COPY . .

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
