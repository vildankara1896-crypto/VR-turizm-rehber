from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import database, models
from .routers import auth, destinations
from .routers import websocket_router, ai, guide, social, analytics


# ─────────────────────────────────────────────
# VERİTABANI TABLOLARINI OLUŞTUR
# ─────────────────────────────────────────────
try:
    models.Base.metadata.create_all(bind=database.engine)
    print("[OK] Veritabani tablolari basariyla kontrol edildi/olusturuldu.")
except Exception as e:
    print(f"[HATA] Veritabani baglanti hatasi: {e}")


# ─────────────────────────────────────────────
# FASTAPI UYGULAMASI
# ─────────────────────────────────────────────
app = FastAPI(
    title="VR Destekli Akıllı Turizm Rehberi API",
    description=(
        "**Vildan KARA** (Back-end) tarafından geliştirilen API.\n\n"
        "### Modüller\n"
        "- **Auth** (Hafta 5): JWT kayıt/giriş, token yenileme, RBAC\n"
        "- **Destinations** (Hafta 5-6): CRUD + PostGIS yakınlık sorgusu\n"
        "- **Occupancy / WebSocket** (Hafta 7): Gerçek zamanlı doluluk verisi\n"
        "- **AI Prediction** (Hafta 9): Kalabalık tahmin modeli\n"
        "- **Smart Guide** (Hafta 10): SSS + NLP + kişiselleştirilmiş öneri\n"
        "- **Social** (Hafta 12): Arkadaş sistemi + %10 indirim kuponu\n"
        "- **Analytics** (Hafta 13): Premium öne çıkarma + işletme paneli\n"
    ),
    version="1.0.0",
    contact={"name": "Vildan KARA", "email": "vildan@example.com"},
)


# ─────────────────────────────────────────────
# CORS (Aleyna'nın Vue.js frontend'i için)
# ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Geliştirme aşamasında; prod'da frontend URL'si yazılır
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# ROUTER'LARI KAYDET
# ─────────────────────────────────────────────

# Hafta 5: Kimlik doğrulama
app.include_router(auth.router)

# Hafta 5-6: Destinasyon CRUD + Yakınlık sorgusu
app.include_router(destinations.router)

# Hafta 7: WebSocket - HTTP doluluk endpoint'leri
app.include_router(websocket_router.http_router)
# Hafta 7: WebSocket - canlı bağlantı endpoint'i
app.include_router(websocket_router.ws_router)

# Hafta 9: AI kalabalık tahmin
app.include_router(ai.router)

# Hafta 10: Akıllı rehber, SSS, öneri
app.include_router(guide.router)

# Hafta 12: Sosyal sistem, arkadaş indirimi
app.include_router(social.router)

# Hafta 13: Premium model, analitik panel
app.include_router(analytics.router)


# ─────────────────────────────────────────────
# SAĞLIK KONTROLÜ
# ─────────────────────────────────────────────

@app.get("/", tags=["Health"])
def health_check():
    """API'nin çalıştığını doğrular."""
    return {
        "status": "ok",
        "message": "VR Turizm Rehberi API'sine Hoş Geldiniz!",
        "version": "1.0.0",
        "docs": "/docs",
    }
