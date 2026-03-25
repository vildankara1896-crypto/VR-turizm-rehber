"""
HAFTA 9: Yapay Zekâ Destekli Kalabalık Tahmin Modeli
──────────────────────────────────────────────────────
Vildan KARA - Backend Geliştirici

Algoritma:
- Geçmiş doluluk loglarından (OccupancyLog) saat bazlı ortalamalar hesaplanır.
- Özellikler: saat (0-23), gün (0=Pazartesi..6=Pazar), tatil durumu.
- Yeterli veri varsa (≥10 kayıt): scikit-learn GradientBoostingRegressor.
- Yetersiz veri varsa: varsayılan turizm deseni kullanılır.
- Tahmin API'si: /api/v1/ai/predict/{destination_id}
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
import datetime

from .. import models, schemas, database

router = APIRouter(
    prefix="/api/v1/ai",
    tags=["AI Kalabalık Tahmini (Hafta 9)"]
)

# Varsayılan turizm doluluk deseni (saat bazlı, 0.0-1.0)
# Sabah açılış, öğle zirvesi, akşam düşüş
DEFAULT_HOURLY_PATTERN = {
    0: 0.03, 1: 0.02, 2: 0.01, 3: 0.01, 4: 0.02, 5: 0.05,
    6: 0.10, 7: 0.20, 8: 0.35, 9: 0.55, 10: 0.70, 11: 0.85,
    12: 0.90, 13: 0.88, 14: 0.80, 15: 0.75, 16: 0.65, 17: 0.55,
    18: 0.40, 19: 0.30, 20: 0.20, 21: 0.12, 22: 0.07, 23: 0.04,
}

# Hafta sonu çarpanı (hafta sonu %25 daha yoğun)
WEEKEND_MULTIPLIER = 1.25
# Tatil çarpanı
HOLIDAY_MULTIPLIER = 1.40


def _crowd_level_label(rate: float) -> str:
    """Doluluk oranını Türkçe kategori etiketine dönüştürür."""
    if rate < 0.25:
        return "Boş"
    elif rate < 0.50:
        return "Normal"
    elif rate < 0.75:
        return "Yoğun"
    else:
        return "Çok Yoğun"


def _get_best_hours(hourly_predictions: dict[int, float], top_n: int = 3) -> list[int]:
    """En düşük doluluk oranına sahip saatleri döndürür (en iyi ziyaret saatleri)."""
    # Sadece açık saatler (08:00–22:00)
    operating = {h: v for h, v in hourly_predictions.items() if 8 <= h <= 22}
    sorted_hours = sorted(operating, key=lambda h: operating[h])
    return sorted_hours[:top_n]


def _predict_with_stats(
    destination_id: int,
    hour: int,
    day_of_week: int,
    is_holiday: bool,
    db: Session
) -> tuple[float, int, str]:
    """
    Geçmiş verilerden istatistiksel tahmin yapar.
    Döndürür: (predicted_rate, data_points, confidence)
    """
    # Aynı saat için tüm geçmiş kayıtları çek
    logs = db.query(models.OccupancyLog).filter(
        models.OccupancyLog.destination_id == destination_id
    ).all()

    if not logs:
        # Hiç veri yok: varsayılan desen
        base = DEFAULT_HOURLY_PATTERN.get(hour, 0.5)
        is_weekend = day_of_week >= 5
        if is_holiday:
            base *= HOLIDAY_MULTIPLIER
        elif is_weekend:
            base *= WEEKEND_MULTIPLIER
        return min(base, 1.0), 0, "Düşük"

    data_count = len(logs)

    # Aynı saat ve gün kombinasyonu için ortalama hesapla
    matching = [
        log.occupancy_rate for log in logs
        if log.timestamp.hour == hour and log.timestamp.weekday() == day_of_week
    ]

    if len(matching) >= 3:
        predicted = sum(matching) / len(matching)
        confidence = "Yüksek" if len(matching) >= 10 else "Orta"
    else:
        # Sadece saat bazlı ortalama
        hour_logs = [log.occupancy_rate for log in logs if log.timestamp.hour == hour]
        if hour_logs:
            base = sum(hour_logs) / len(hour_logs)
        else:
            base = DEFAULT_HOURLY_PATTERN.get(hour, 0.5)

        is_weekend = day_of_week >= 5
        if is_holiday:
            base *= HOLIDAY_MULTIPLIER
        elif is_weekend:
            base *= WEEKEND_MULTIPLIER

        predicted = min(base, 1.0)
        confidence = "Orta" if hour_logs else "Düşük"

    return min(predicted, 1.0), data_count, confidence


def _predict_with_sklearn(
    destination_id: int,
    hour: int,
    day_of_week: int,
    is_holiday: bool,
    db: Session
) -> tuple[float, int, str]:
    """
    scikit-learn GradientBoostingRegressor ile tahmin yapar.
    Yeterli veri yoksa _predict_with_stats'a düşer.
    """
    try:
        from sklearn.ensemble import GradientBoostingRegressor
        import numpy as np
    except ImportError:
        return _predict_with_stats(destination_id, hour, day_of_week, is_holiday, db)

    logs = db.query(models.OccupancyLog).filter(
        models.OccupancyLog.destination_id == destination_id
    ).all()

    if len(logs) < 10:
        return _predict_with_stats(destination_id, hour, day_of_week, is_holiday, db)

    # Feature engineering: saat, gün, hafta sonu mu, tatil mi
    X = np.array([
        [
            log.timestamp.hour,
            log.timestamp.weekday(),
            1 if log.timestamp.weekday() >= 5 else 0,
            0,  # is_holiday — geçmiş veriler için 0 varsayılır
        ]
        for log in logs
    ])
    y = np.array([log.occupancy_rate for log in logs])

    model = GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=42)
    model.fit(X, y)

    X_pred = np.array([[hour, day_of_week, 1 if day_of_week >= 5 else 0, int(is_holiday)]])
    predicted = float(model.predict(X_pred)[0])
    predicted = max(0.0, min(1.0, predicted))

    return predicted, len(logs), "Yüksek"


# ─────────────────────────────────────────────
# ENDPOINT: TAHMİN
# ─────────────────────────────────────────────

@router.post("/predict/{destination_id}", response_model=schemas.PredictionResponse)
def predict_occupancy(
    destination_id: int,
    request: schemas.PredictionRequest,
    db: Session = Depends(database.get_db)
):
    """
    Belirtilen mekan için gelecekteki doluluk tahmini yapar.

    - 10'dan az geçmiş veri varsa: istatistiksel model (saatlik ortalama + turizm deseni)
    - 10+ veri varsa ve scikit-learn kuruluysa: GradientBoostingRegressor
    - Her iki durumda da en iyi ziyaret saatleri hesaplanır.
    """
    # Mekan var mı?
    destination = db.query(models.Destination).filter(
        models.Destination.id == destination_id
    ).first()
    if not destination:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mekan bulunamadı.")

    if request.hour < 0 or request.hour > 23:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Saat 0-23 arasında olmalı.")
    if request.day_of_week < 0 or request.day_of_week > 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gün 0-6 arasında olmalı.")

    # Tahmin yap
    predicted, data_points, confidence = _predict_with_sklearn(
        destination_id, request.hour, request.day_of_week, request.is_holiday, db
    )

    # Tüm günün saatlik tahminlerini hesapla (en iyi saatleri bulmak için)
    hourly_preds: dict[int, float] = {}
    for h in range(24):
        rate, _, _ = _predict_with_stats(destination_id, h, request.day_of_week, request.is_holiday, db)
        hourly_preds[h] = rate

    best_hours = _get_best_hours(hourly_preds)

    return schemas.PredictionResponse(
        destination_id=destination_id,
        predicted_occupancy=round(predicted, 3),
        crowd_level=_crowd_level_label(predicted),
        best_visit_hours=best_hours,
        confidence=confidence,
        data_points_used=data_points,
    )


@router.get("/predict/{destination_id}/schedule", tags=["AI Kalabalık Tahmini (Hafta 9)"])
def predict_daily_schedule(
    destination_id: int,
    day_of_week: int = 0,
    is_holiday: bool = False,
    db: Session = Depends(database.get_db)
):
    """
    Belirtilen gün için saatlik doluluk tahmin tablosunu döndürür.
    Frontend dashboard'u ve kullanıcı planlama ekranı için kullanılır.
    """
    destination = db.query(models.Destination).filter(
        models.Destination.id == destination_id
    ).first()
    if not destination:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mekan bulunamadı.")

    schedule = []
    for hour in range(24):
        rate, data_points, confidence = _predict_with_stats(
            destination_id, hour, day_of_week, is_holiday, db
        )
        schedule.append({
            "hour": hour,
            "predicted_occupancy": round(rate, 3),
            "crowd_level": _crowd_level_label(rate),
        })

    day_names = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

    return {
        "destination_id": destination_id,
        "destination_name": destination.name,
        "day_of_week": day_of_week,
        "day_name": day_names[day_of_week],
        "is_holiday": is_holiday,
        "hourly_schedule": schedule,
        "recommended_visit_hours": _get_best_hours(
            {item["hour"]: item["predicted_occupancy"] for item in schedule}
        ),
    }
