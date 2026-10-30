FROM python:3.12-slim
WORKDIR /srv/backend
COPY backend/requirements-integration.lock.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
ENV PORT=8000 HOST=0.0.0.0 MODEL_MODE=real ENABLED_MODELS=measurements,model4
EXPOSE 8000
CMD ["python", "app.py"]
