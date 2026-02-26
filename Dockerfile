FROM python:3.10-slim

WORKDIR /app

# Instala as dependências do sistema necessárias para o Django e Gunicorn
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# Coleta os arquivos estáticos e prepara o banco na hora de construir a imagem
RUN python manage.py collectstatic --noinput
RUN python manage.py migrate

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "backend.wsgi:application"]