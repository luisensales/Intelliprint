# IntelliPrint Web - Contenedor de Producción
FROM python:3.11-slim

# Evitar prompts y buffering
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Instalar dependencias del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt httpx

# Copiar el código del proyecto
COPY . .

# Crear carpetas de trabajo con permisos
RUN mkdir -p uploads jobs static icc_profiles worksheets hotfolder/in hotfolder/processing hotfolder/out_aprobados hotfolder/out_rechazados

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

