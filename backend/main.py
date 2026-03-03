from fastapi import FastAPI
from . import database, models
from .routers import auth, destinations 


try:
    models.Base.metadata.create_all(bind=database.engine)
    print("Veritabanı tabloları başarıyla kontrol edildi/oluşturuldu.")
except Exception as e:
    print(f"Veritabanı bağlantısı veya tablo oluşturma hatası: {e}")


app = FastAPI(
    title="VR Destekli Akıllı Turizm Rehberi API",
    description="Vildan KARA (Back-end) tarafından geliştirilmektedir.",
    version="0.1.0"
)


app.include_router(auth.router)



@app.get("/")
def read_root():
    """
    Ana karşılama endpoint'i.
    API'nin çalıştığını doğrulamak için.
    """
    return {"message": "VR Turizm Rehberi API'sine Hoş Geldiniz!"}
