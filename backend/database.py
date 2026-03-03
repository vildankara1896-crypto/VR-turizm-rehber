from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Bu veritabanı adresi, Buse Hanım'ın Docker'da kurduğu
# PostgreSQL sunucusuna bağlanmak içindir.
# Planınızda PostGIS gerektiği için veritabanı türü postgresql'dir.
# Şimdilik bu şekilde kalabilir, Buse Hanım gerekirse localhost yerine
# 'db' (docker servis adı) yazmanızı söyleyebilir.
DATABASE_URL = "postgresql://user:password@localhost:5432/turizmdb"
# Not: Gerçek kullanıcı adı, şifre ve veritabanı adını
# Buse Hanım'ın docker-compose.yml dosyasındaki ayarlara göre
# güncellemeniz gerekecek.

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Bu fonksiyon, API endpoint'lerinde (Hafta 4-5) veritabanı bağlantısı
# açmak ve kapatmak için kullanılacak.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()