from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from geoalchemy2.shape import from_shape
from geoalchemy2.functions import ST_DWithin, ST_MakePoint, ST_SetSRID, ST_Distance
from shapely.geometry import Point
from typing import List, Optional

from .. import models, schemas, database, security

SRID = 4326

router = APIRouter(
    prefix="/api/v1/destinations",
    tags=["Destinations (Hafta 5 & 6)"]
)


# ─────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────

def get_destination_by_id(db: Session, destination_id: int) -> models.Destination:
    """ID ile destinasyonu çeker; bulunamazsa 404 döndürür."""
    destination = db.query(models.Destination).filter(
        models.Destination.id == destination_id
    ).first()
    if not destination:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Destinasyon bulunamadı."
        )
    return destination


def update_destination_rating(destination_id: int, db: Session):
    """Yeni yorum eklendikten sonra ortalama puanı günceller."""
    avg_rating = db.query(func.avg(models.Review.rating)).filter(
        models.Review.destination_id == destination_id
    ).scalar()

    destination = get_destination_by_id(db, destination_id)
    destination.average_rating = float(avg_rating) if avg_rating is not None else 0.0
    db.commit()


# ─────────────────────────────────────────────
# HAFTA 5: DESTINATIONS CRUD
# ─────────────────────────────────────────────

@router.post("/", response_model=schemas.Destination, status_code=status.HTTP_201_CREATED)
def create_destination(
    destination: schemas.DestinationCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.get_current_active_user)
):
    """Yeni destinasyon oluşturur. (Giriş zorunlu)"""
    point = Point(destination.longitude, destination.latitude)
    location_wkb = from_shape(point, srid=SRID)

    db_destination = models.Destination(
        **destination.model_dump(exclude={"latitude", "longitude"}),
        location=location_wkb
    )
    db.add(db_destination)
    db.commit()
    db.refresh(db_destination)
    return db_destination


@router.get("/", response_model=List[schemas.DestinationWithCoords])
def read_destinations(
    category: Optional[str] = Query(None, description="Kategoriye göre filtrele"),
    db: Session = Depends(database.get_db)
):
    """
    Tüm destinasyonları listeler. Koordinatlar da döndürülür (harita markerları için).
    Opsiyonel: category filtresi.
    """
    query = db.query(
        models.Destination.id,
        models.Destination.name,
        models.Destination.address,
        models.Destination.description,
        models.Destination.category,
        models.Destination.ticket_price,
        models.Destination.vr_image_url,
        models.Destination.opening_hours,
        models.Destination.average_rating,
        models.Destination.is_premium,
        func.ST_Y(models.Destination.location).label("latitude"),
        func.ST_X(models.Destination.location).label("longitude"),
    )

    if category:
        query = query.filter(models.Destination.category == category)

    # Premium destinasyonlar listenin başında gelir (Hafta 13)
    rows = query.order_by(models.Destination.is_premium.desc()).all()

    return [schemas.DestinationWithCoords.model_validate(row) for row in rows]


@router.get("/{destination_id}", response_model=schemas.DestinationWithCoords)
def read_destination(destination_id: int, db: Session = Depends(database.get_db)):
    """Tek bir destinasyonun tüm detaylarını döndürür."""
    row = db.query(
        models.Destination.id,
        models.Destination.name,
        models.Destination.address,
        models.Destination.description,
        models.Destination.category,
        models.Destination.ticket_price,
        models.Destination.vr_image_url,
        models.Destination.opening_hours,
        models.Destination.average_rating,
        models.Destination.is_premium,
        func.ST_Y(models.Destination.location).label("latitude"),
        func.ST_X(models.Destination.location).label("longitude"),
    ).filter(models.Destination.id == destination_id).first()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Destinasyon bulunamadı.")

    return schemas.DestinationWithCoords.model_validate(row)


@router.put("/{destination_id}", response_model=schemas.Destination)
def update_destination(
    destination_id: int,
    destination_update: schemas.DestinationCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.get_current_active_user)
):
    """Destinasyon bilgilerini günceller. (Giriş zorunlu)"""
    db_destination = get_destination_by_id(db, destination_id)
    update_data = destination_update.model_dump(exclude_unset=True)

    if "latitude" in update_data and "longitude" in update_data:
        new_lat = update_data.pop("latitude")
        new_lon = update_data.pop("longitude")
        db_destination.location = from_shape(Point(new_lon, new_lat), srid=SRID)

    for key, value in update_data.items():
        setattr(db_destination, key, value)

    db.commit()
    db.refresh(db_destination)
    return db_destination


@router.delete("/{destination_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_destination(
    destination_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.require_role("admin", "business"))
):
    """Destinasyonu siler. (Admin veya Business rolü zorunlu)"""
    db_destination = get_destination_by_id(db, destination_id)
    db.delete(db_destination)
    db.commit()


# ─────────────────────────────────────────────
# HAFTA 6: YAKINLIK SORGUSU (PostGIS ST_DWithin)
# ─────────────────────────────────────────────

@router.post("/nearby", response_model=List[schemas.DestinationWithCoords], tags=["Nearby (Hafta 6)"])
def find_nearby_destinations(query: schemas.NearbyQuery, db: Session = Depends(database.get_db)):
    """
    Kullanıcının konumuna belirli bir yarıçap içindeki destinasyonları bulur.
    PostGIS ST_DWithin fonksiyonu kullanır (GiST indeksiyle optimize).

    - radius_km: kilometre cinsinden arama yarıçapı (varsayılan: 5 km)
    - category: opsiyonel kategori filtresi
    """
    # Kullanıcının konumunu PostGIS geometrisine dönüştür
    user_point = ST_SetSRID(ST_MakePoint(query.longitude, query.latitude), SRID)

    # 1 derece ≈ 111.195 km (enlem için); ST_DWithin derece cinsinden çalışır
    radius_degrees = query.radius_km / 111.195

    base_query = db.query(
        models.Destination.id,
        models.Destination.name,
        models.Destination.address,
        models.Destination.description,
        models.Destination.category,
        models.Destination.ticket_price,
        models.Destination.vr_image_url,
        models.Destination.opening_hours,
        models.Destination.average_rating,
        models.Destination.is_premium,
        func.ST_Y(models.Destination.location).label("latitude"),
        func.ST_X(models.Destination.location).label("longitude"),
        ST_Distance(models.Destination.location, user_point).label("distance_deg"),
    ).filter(
        ST_DWithin(models.Destination.location, user_point, radius_degrees)
    )

    if query.category:
        base_query = base_query.filter(models.Destination.category == query.category)

    # En yakından en uzağa sırala; premium önce göster
    rows = base_query.order_by(
        models.Destination.is_premium.desc(),
        "distance_deg"
    ).all()

    return [schemas.DestinationWithCoords.model_validate(row) for row in rows]


# ─────────────────────────────────────────────
# HAFTA 6: YORUMLAR (Reviews)
# ─────────────────────────────────────────────

@router.post(
    "/{destination_id}/reviews",
    response_model=schemas.Review,
    status_code=status.HTTP_201_CREATED,
    tags=["Reviews (Hafta 6)"]
)
def create_review(
    destination_id: int,
    review: schemas.ReviewBase,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.get_current_active_user)
):
    """Destinasyona yorum ve puan ekler. Aynı kullanıcı ikinci kez yorum yapamaz."""
    get_destination_by_id(db, destination_id)

    existing = db.query(models.Review).filter(
        models.Review.destination_id == destination_id,
        models.Review.user_id == current_user.id
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu destinasyona zaten yorum yaptınız."
        )

    db_review = models.Review(
        **review.model_dump(),
        destination_id=destination_id,
        user_id=current_user.id
    )
    db.add(db_review)
    db.commit()
    db.refresh(db_review)

    update_destination_rating(destination_id, db)
    return db_review


@router.get(
    "/{destination_id}/reviews",
    response_model=List[schemas.Review],
    tags=["Reviews (Hafta 6)"]
)
def get_reviews(destination_id: int, db: Session = Depends(database.get_db)):
    """Destinasyona ait tüm yorumları en yeniden eskiye listeler."""
    return db.query(models.Review).filter(
        models.Review.destination_id == destination_id
    ).order_by(models.Review.created_at.desc()).all()
