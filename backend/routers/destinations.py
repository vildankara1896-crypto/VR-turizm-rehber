from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func 
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from typing import List

# Kendi dosyalarımızdan importlar
from .. import models, schemas, database, security 

# PostGIS için SRID
SRID = 4326 

# --- ROUTER TANIMI ---

router = APIRouter(
    prefix="/api/v1/destinations",
    tags=["Destinations (Hafta 5 & 6)"]
)

# Database session bağımlılığı (Dependency)
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- YARDIMCI FONKSİYONLAR ---

def get_destination_by_id(db: Session, destination_id: int):
    """Belirtilen ID ile destinasyonu çeker ve yoksa 404 döndürür."""
    destination = db.query(models.Destination).filter(models.Destination.id == destination_id).first()
    if not destination:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Destinasyon bulunamadı.")
    return destination

def update_destination_rating(destination_id: int, db: Session):
    """HAFTA 6 GÖREVİ: Yeni yorum yapıldığında ortalama puanı günceller."""
    # SQLAlchemy func.avg kullanarak ortalama hesaplanır
    avg_rating = db.query(func.avg(models.Review.rating)).filter(
        models.Review.destination_id == destination_id
    ).scalar()
    
    destination = get_destination_by_id(db, destination_id)
    
    if destination:
        destination.average_rating = avg_rating if avg_rating is not None else 0.0
        db.commit()

# --- DESTINATIONS API (HAFTA 5) ---

@router.post("/", response_model=schemas.Destination, status_code=status.HTTP_201_CREATED)
def create_destination(
    destination: schemas.DestinationCreate, 
    db: Session = Depends(get_db),
    # Yetkilendirme (Admin/Yetkili Kullanıcı zorunluluğu)
    current_user: models.User = Depends(security.get_current_active_user) 
):
    """Yeni destinasyon oluşturur."""
    # Enlem ve Boylamı PostGIS'in anlayacağı geometri (Point) tipine dönüştürme
    point = Point(destination.longitude, destination.latitude)
    location_wkb = from_shape(point, srid=SRID)
    
    db_destination = models.Destination(
        **destination.model_dump(exclude={'latitude', 'longitude'}),
        location=location_wkb
    )
    
    db.add(db_destination)
    db.commit()
    db.refresh(db_destination)
    
    return db_destination

@router.get("/", response_model=List[schemas.Destination])
def read_destinations(db: Session = Depends(get_db)):
    """HAFTA 5 GÖREVİ: Tüm destinasyonları harita için optimize edilmiş olarak listeler."""
    
    # OPTİMİZE EDİLMİŞ POSTGIS SORGUSU: Sadece gerekli alanları ve konumu çeker.
    destinations_data = db.query(
        models.Destination.id,
        models.Destination.name,
        models.Destination.category,
        models.Destination.average_rating,
        func.ST_Y(models.Destination.location).label("latitude"), # Enlem (Latitude)
        func.ST_X(models.Destination.location).label("longitude") # Boylam (Longitude)
    ).all()
    
    # SQLAlchemy'nin döndürdüğü 'Row' nesnelerini Pydantic listesine dönüştürür.
    return [schemas.Destination.model_validate(row) for row in destinations_data]

@router.get("/{destination_id}", response_model=schemas.Destination)
def read_destination(destination_id: int, db: Session = Depends(get_db)):
    """Tek bir destinasyonun detaylarını döndürür."""
    return get_destination_by_id(db, destination_id)

@router.put("/{destination_id}", response_model=schemas.Destination)
def update_destination(
    destination_id: int,
    destination_update: schemas.DestinationCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_active_user) 
):
    """Destinasyon bilgilerini günceller."""
    db_destination = get_destination_by_id(db, destination_id)
    update_data = destination_update.model_dump(exclude_unset=True)

    # Coğrafi Konumu Güncelleme
    if 'latitude' in update_data and 'longitude' in update_data:
        new_lat = update_data.pop('latitude')
        new_lon = update_data.pop('longitude')
        point = Point(new_lon, new_lat)
        db_destination.location = from_shape(point, srid=SRID)
    
    # Kalan alanları güncelleme
    for key, value in update_data.items():
        setattr(db_destination, key, value)
    
    db.commit()
    db.refresh(db_destination)
    return db_destination

@router.delete("/{destination_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_destination(
    destination_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_active_user)
):
    """Destinasyonu siler."""
    db_destination = get_destination_by_id(db, destination_id)
    db.delete(db_destination)
    db.commit()
    return 

# --- REVIEWS API (HAFTA 6) ---

@router.post("/{destination_id}/reviews", 
             response_model=schemas.Review, 
             status_code=status.HTTP_201_CREATED,
             tags=["Reviews"])
def create_review_for_destination(
    destination_id: int,
    review: schemas.ReviewBase,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_active_user) 
):
    """Yorum ve puan ekler."""
    
    # Kontrol: Aynı destinasyona sadece bir yorum yapılabilir.
    existing_review = db.query(models.Review).filter(
        models.Review.destination_id == destination_id,
        models.Review.user_id == current_user.id
    ).first()
    
    if existing_review:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu destinasyona zaten yorum yaptınız.")

    # Yorumu oluştur
    db_review = models.Review(
        **review.model_dump(),
        destination_id=destination_id,
        user_id=current_user.id
    )
    
    db.add(db_review)
    db.commit()
    db.refresh(db_review)

    # Ortak Görev: Ortalama Puanı Güncelle
    update_destination_rating(destination_id, db)
    
    return db_review

@router.get("/{destination_id}/reviews", 
            response_model=List[schemas.Review],
            tags=["Reviews"])
def get_reviews_for_destination(destination_id: int, db: Session = Depends(get_db)):
    """Bir destinasyona ait tüm yorumları listeler."""
    reviews = db.query(models.Review).filter(
        models.Review.destination_id == destination_id
    ).order_by(models.Review.created_at.desc()).all()
    
    return reviews