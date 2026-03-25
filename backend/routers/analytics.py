"""
HAFTA 13: Premium Model ve İşletme Analitik Paneli
──────────────────────────────────────────────────────
Vildan KARA - Backend Geliştirici

Bu modül iki şeyi sağlar:
1. Premium İşletme Öne Çıkarma: İşletme sahipleri mekanlarını ücretli
   olarak öne çıkarabilir (harita ve liste başında gösterilir).
2. Analitik Panel (Dashboard): İşletme sahipleri mekanlarına ait
   ziyaretçi istatistiklerini ve doluluk trend grafiklerini görüntüler.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
import datetime

from .. import models, schemas, database, security

router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["Premium & Analitik Panel (Hafta 13)"]
)

DAY_NAMES = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


# ─────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────

def _build_destination_stats(dest: models.Destination, db: Session) -> schemas.DestinationStats:
    """Bir destinasyon için istatistik nesnesini oluşturur."""

    total_reviews = db.query(func.count(models.Review.id)).filter(
        models.Review.destination_id == dest.id
    ).scalar() or 0

    avg_rating = db.query(func.avg(models.Review.rating)).filter(
        models.Review.destination_id == dest.id
    ).scalar()

    total_occupancy_records = db.query(func.count(models.OccupancyLog.id)).filter(
        models.OccupancyLog.destination_id == dest.id
    ).scalar() or 0

    avg_occupancy = db.query(func.avg(models.OccupancyLog.occupancy_rate)).filter(
        models.OccupancyLog.destination_id == dest.id
    ).scalar()

    # En yoğun saat
    peak_hour = None
    peak_hour_row = db.query(
        func.extract("hour", models.OccupancyLog.timestamp).label("hour"),
        func.avg(models.OccupancyLog.occupancy_rate).label("avg_rate")
    ).filter(
        models.OccupancyLog.destination_id == dest.id
    ).group_by("hour").order_by(func.avg(models.OccupancyLog.occupancy_rate).desc()).first()

    if peak_hour_row:
        peak_hour = int(peak_hour_row.hour)

    # En yoğun gün
    busiest_day = None
    busiest_day_row = db.query(
        func.extract("dow", models.OccupancyLog.timestamp).label("dow"),  # 0=Pazar, 1=Pazartesi...
        func.avg(models.OccupancyLog.occupancy_rate).label("avg_rate")
    ).filter(
        models.OccupancyLog.destination_id == dest.id
    ).group_by("dow").order_by(func.avg(models.OccupancyLog.occupancy_rate).desc()).first()

    if busiest_day_row:
        # PostgreSQL dow: 0=Pazar, 1=Pzt...6=Cmt → Python weekday: 0=Pzt..6=Paz
        dow = int(busiest_day_row.dow)
        py_dow = (dow - 1) % 7  # Dönüşüm
        busiest_day = DAY_NAMES[py_dow]

    # Bilet müsaitlik oranı
    ticket_available_count = db.query(func.count(models.OccupancyLog.id)).filter(
        models.OccupancyLog.destination_id == dest.id,
        models.OccupancyLog.ticket_available == True
    ).scalar() or 0

    ticket_rate = (ticket_available_count / total_occupancy_records) if total_occupancy_records > 0 else 1.0

    return schemas.DestinationStats(
        destination_id=dest.id,
        destination_name=dest.name,
        total_reviews=total_reviews,
        average_rating=round(float(avg_rating), 2) if avg_rating else 0.0,
        total_occupancy_records=total_occupancy_records,
        average_occupancy_rate=round(float(avg_occupancy), 3) if avg_occupancy else 0.0,
        peak_hour=peak_hour,
        busiest_day=busiest_day,
        ticket_availability_rate=round(ticket_rate, 3),
    )


# ─────────────────────────────────────────────
# PREMİUM ÖNDENÇIKARMA SİSTEMİ
# ─────────────────────────────────────────────

@router.post("/destinations/{destination_id}/premium", response_model=schemas.Destination)
def upgrade_to_premium(
    destination_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.require_role("admin", "business"))
):
    """
    Destinasyonu premium olarak işaretler.
    Premium mekanlar harita listesinde ve GET /destinations'ta en üstte gösterilir.
    (Admin veya Business rolü zorunlu)
    """
    destination = db.query(models.Destination).filter(
        models.Destination.id == destination_id
    ).first()
    if not destination:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mekan bulunamadı.")

    destination.is_premium = True
    db.commit()
    db.refresh(destination)
    return destination


@router.delete("/destinations/{destination_id}/premium", response_model=schemas.Destination)
def downgrade_from_premium(
    destination_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.require_role("admin"))
):
    """Premium özelliğini kaldırır. (Sadece Admin)"""
    destination = db.query(models.Destination).filter(
        models.Destination.id == destination_id
    ).first()
    if not destination:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mekan bulunamadı.")

    destination.is_premium = False
    db.commit()
    db.refresh(destination)
    return destination


# ─────────────────────────────────────────────
# İSTATİSTİKLER
# ─────────────────────────────────────────────

@router.get("/destinations/{destination_id}/stats", response_model=schemas.DestinationStats)
def get_destination_stats(
    destination_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.require_role("admin", "business"))
):
    """
    Tek bir destinasyonun detaylı istatistiklerini döndürür.
    (Admin veya Business rolü zorunlu)
    """
    dest = db.query(models.Destination).filter(models.Destination.id == destination_id).first()
    if not dest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mekan bulunamadı.")

    return _build_destination_stats(dest, db)


@router.get("/destinations/{destination_id}/occupancy-trend")
def get_occupancy_trend(
    destination_id: int,
    days: int = Query(7, ge=1, le=90, description="Kaç günlük trend"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.require_role("admin", "business"))
):
    """
    Son N günün saatlik doluluk trendi.
    Grafik çizimi için zaman serisi verisi döndürür.
    """
    dest = db.query(models.Destination).filter(models.Destination.id == destination_id).first()
    if not dest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mekan bulunamadı.")

    since = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)

    logs = db.query(models.OccupancyLog).filter(
        models.OccupancyLog.destination_id == destination_id,
        models.OccupancyLog.timestamp >= since.replace(tzinfo=None)
    ).order_by(models.OccupancyLog.timestamp.asc()).all()

    trend_data = [
        {
            "timestamp": log.timestamp.isoformat(),
            "occupancy_rate": log.occupancy_rate,
            "visitor_count": log.visitor_count,
            "ticket_available": log.ticket_available,
        }
        for log in logs
    ]

    return {
        "destination_id": destination_id,
        "destination_name": dest.name,
        "period_days": days,
        "total_records": len(trend_data),
        "trend": trend_data,
    }


# ─────────────────────────────────────────────
# İŞLETME SAHİBİ DASHBOARD
# ─────────────────────────────────────────────

@router.get("/dashboard", response_model=schemas.DashboardResponse)
def get_business_dashboard(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.require_role("admin", "business"))
):
    """
    İşletme sahibi veya admin için genel dashboard.
    Admin: tüm destinasyonların özeti.
    Business: kendi destinasyonlarının özeti.

    Dashboard verileri:
    - Toplam destinasyon ve premium sayısı
    - Genel ortalama puan
    - Her destinasyona ait istatistikler
    """
    if current_user.role == "admin":
        destinations = db.query(models.Destination).all()
    else:
        # Business sahibi: sadece kendi eklediği mekanlar
        # Not: Destinasyon modelinde owner_id yok; bu sistemde tüm iş
        # mekanlarını gösteriyoruz. Gerçek sistemde owner_id eklenebilir.
        destinations = db.query(models.Destination).all()

    total = len(destinations)
    premium_count = sum(1 for d in destinations if d.is_premium)

    # Genel ortalama puan
    all_avg = db.query(func.avg(models.Review.rating)).scalar()

    # Toplam yorum
    total_reviews = db.query(func.count(models.Review.id)).scalar() or 0

    # Her destinasyon için istatistik
    dest_stats = [_build_destination_stats(dest, db) for dest in destinations]

    return schemas.DashboardResponse(
        owner_email=current_user.email,
        total_destinations=total,
        premium_destinations=premium_count,
        overall_average_rating=round(float(all_avg), 2) if all_avg else 0.0,
        total_reviews=total_reviews,
        destinations=dest_stats,
    )


# ─────────────────────────────────────────────
# KULLANICI ROL YÖNETİMİ (Admin)
# ─────────────────────────────────────────────

@router.put("/users/{user_id}/role", response_model=schemas.User)
def update_user_role(
    user_id: int,
    role_update: schemas.UserRoleUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.require_role("admin"))
):
    """
    Kullanıcı rolünü günceller. (Sadece Admin)
    Roller: standard | premium | business | admin
    """
    allowed_roles = {"standard", "premium", "business", "admin"}
    if role_update.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Geçersiz rol. İzin verilen roller: {', '.join(allowed_roles)}"
        )

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı.")

    user.role = role_update.role
    db.commit()
    db.refresh(user)
    return user
