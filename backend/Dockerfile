# Python 3.10 sürümünü kullanıyoruz
FROM python:3.10-slim

# Konteyner içindeki çalışma klasörümüz
WORKDIR /app

# Önce gereksinim dosyasını kopyalayıp kütüphaneleri kuruyoruz
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kalan tüm proje dosyalarını kopyalıyoruz
COPY . .

# Sunucuyu başlatıyoruz (Host 0.0.0.0 olmalı ki dışarıdan erişilebilsin)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
