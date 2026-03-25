"""
HAFTA 7: WebSocket ile Gerçek Zamanlı Veri Aktarımı
──────────────────────────────────────────────────────
Vildan KARA - Backend Geliştirici

Bu modül iki şeyi sağlar:
1. WebSocket endpoint: Frontend mekanın anlık doluluk bilgisine abone olur.
   Sunucu her 5 saniyede bir güncel doluluk oranını yayınlar.
2. HTTP POST endpoint: IoT cihazları veya admin paneli doluluk güncellemesi gönderir.
   Yeni veri geldiğinde tüm abone istemcilere anında broadcast yapılır.
"""

import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas, database, security


# ─────────────────────────────────────────────
# BAĞLANTI YÖNETİCİSİ (Connection Manager)
# ─────────────────────────────────────────────

class ConnectionManager:
    """
    Aktif WebSocket bağlantılarını destinasyon bazında tutar.
    Bir mekan için birden fazla istemci (kullanıcı) bağlanabilir.
    """

    def __init__(self):
        # {destination_id: [WebSocket, WebSocket, ...]}
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, destination_id: int):
        await websocket.accept()
        if destination_id not in self.active_connections:
            self.active_connections[destination_id] = []
        self.active_connections[destination_id].append(websocket)

    def disconnect(self, websocket: WebSocket, destination_id: int):
        if destination_id in self.active_connections:
            if websocket in self.active_connections[destination_id]:
                self.active_connections[destination_id].remove(websocket)

    async def broadcast_to_destination(self, destination_id: int, data: dict):
        """Belirli bir mekanı dinleyen tüm istemcilere veri gönderir."""
        if destination_id not in self.active_connections:
            return
        dead_connections = []
        for connection in self.active_connections[destination_id]:
            try:
                await connection.send_json(data)
            except Exception:
                dead_connections.append(connection)
        for dead in dead_connections:
            self.disconnect(dead, destination_id)

    def active_subscriber_count(self, destination_id: int) -> int:
        return len(self.active_connections.get(destination_id, []))


manager = ConnectionManager()


# ─────────────────────────────────────────────
# ROUTER TANIMLARI
# ─────────────────────────────────────────────

# HTTP endpoint'ler için router (doluluk güncelleme, anlık sorgulama)
http_router = APIRouter(
    prefix="/api/v1/occupancy",
    tags=["Occupancy / WebSocket (Hafta 7)"]
)

# WebSocket endpoint'ler için router (prefix yok, /ws ile başlar)
ws_router = APIRouter(tags=["WebSocket Live Feed (Hafta 7)"])


# ─────────────────────────────────────────────
# HTTP ENDPOINT: DOLULUK GÜNCELLEME (IoT/Admin)
# ─────────────────────────────────────────────

@http_router.post("/{destination_id}", response_model=schemas.OccupancyResponse)
async def update_occupancy(
    destination_id: int,
    occupancy: schemas.OccupancyCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.require_role("admin", "business"))
):
    """
    Mekanın anlık doluluk oranını günceller.
    (Admin veya Business rolü gerekir — IoT cihazı veya işletme sahibi tarafından çağrılır)

    Yeni veri kaydedildiğinde o mekanı dinleyen tüm WebSocket istemcilerine
    otomatik olarak broadcast yapılır.
    """
    # Mekan var mı kontrol et
    destination = db.query(models.Destination).filter(
        models.Destination.id == destination_id
    ).first()
    if not destination:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mekan bulunamadı.")

    # Veritabanına kaydet
    log = models.OccupancyLog(
        destination_id=destination_id,
        occupancy_rate=occupancy.occupancy_rate,
        visitor_count=occupancy.visitor_count,
        ticket_available=occupancy.ticket_available,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    # Abone istemcilere gerçek zamanlı broadcast
    broadcast_data = {
        "event": "occupancy_update",
        "destination_id": destination_id,
        "occupancy_rate": occupancy.occupancy_rate,
        "visitor_count": occupancy.visitor_count,
        "ticket_available": occupancy.ticket_available,
        "timestamp": log.timestamp.isoformat(),
    }
    await manager.broadcast_to_destination(destination_id, broadcast_data)

    return log


@http_router.get("/{destination_id}/current", response_model=schemas.OccupancyResponse)
def get_current_occupancy(destination_id: int, db: Session = Depends(database.get_db)):
    """Mekanın en güncel doluluk kaydını döndürür."""
    log = db.query(models.OccupancyLog).filter(
        models.OccupancyLog.destination_id == destination_id
    ).order_by(models.OccupancyLog.timestamp.desc()).first()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bu mekan için doluluk verisi henüz yok."
        )
    return log


@http_router.get("/{destination_id}/history", response_model=list[schemas.OccupancyResponse])
def get_occupancy_history(
    destination_id: int,
    limit: int = 50,
    db: Session = Depends(database.get_db)
):
    """Mekanın doluluk geçmişini döndürür (en yeniden eskiye, max 50 kayıt)."""
    logs = db.query(models.OccupancyLog).filter(
        models.OccupancyLog.destination_id == destination_id
    ).order_by(models.OccupancyLog.timestamp.desc()).limit(limit).all()
    return logs


# ─────────────────────────────────────────────
# WEBSOCKET ENDPOINT: CANLI ABONE
# ─────────────────────────────────────────────

@ws_router.websocket("/ws/destinations/{destination_id}/live")
async def websocket_live_occupancy(websocket: WebSocket, destination_id: int):
    """
    WebSocket bağlantısı: Mekanın canlı doluluk verisine abone olur.

    Bağlandıktan sonra:
    - Sunucu her 10 saniyede bir veritabanından güncel doluluk verisini push eder.
    - HTTP POST /api/v1/occupancy/{id} üzerinden yeni veri geldiğinde anında iletilir.
    - Bağlantı koptuğunda (kullanıcı sayfadan ayrılırsa) temiz kapatılır.

    Örnek mesaj formatı:
    {
        "event": "occupancy_update",
        "destination_id": 1,
        "occupancy_rate": 0.75,
        "visitor_count": 150,
        "ticket_available": true,
        "timestamp": "2026-03-25T14:30:00"
    }
    """
    db = database.SessionLocal()
    try:
        await manager.connect(websocket, destination_id)

        # Bağlanır bağlanmaz anlık veriyi gönder
        latest = db.query(models.OccupancyLog).filter(
            models.OccupancyLog.destination_id == destination_id
        ).order_by(models.OccupancyLog.timestamp.desc()).first()

        if latest:
            await websocket.send_json({
                "event": "initial_state",
                "destination_id": destination_id,
                "occupancy_rate": latest.occupancy_rate,
                "visitor_count": latest.visitor_count,
                "ticket_available": latest.ticket_available,
                "timestamp": latest.timestamp.isoformat(),
            })
        else:
            await websocket.send_json({
                "event": "no_data",
                "destination_id": destination_id,
                "message": "Bu mekan için henüz doluluk verisi yok.",
            })

        # Polling: 10 saniyede bir güncel veri gönder
        while True:
            await asyncio.sleep(10)

            db.expire_all()  # Önbelleği temizle, güncel veriyi çek
            current = db.query(models.OccupancyLog).filter(
                models.OccupancyLog.destination_id == destination_id
            ).order_by(models.OccupancyLog.timestamp.desc()).first()

            if current:
                await websocket.send_json({
                    "event": "occupancy_update",
                    "destination_id": destination_id,
                    "occupancy_rate": current.occupancy_rate,
                    "visitor_count": current.visitor_count,
                    "ticket_available": current.ticket_available,
                    "timestamp": current.timestamp.isoformat(),
                })

    except WebSocketDisconnect:
        # İstemci bağlantıyı kapattı — temiz lifecycle yönetimi
        manager.disconnect(websocket, destination_id)
    finally:
        db.close()
