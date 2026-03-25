from pydantic import BaseModel, EmailStr, ConfigDict
from typing import List, Optional
import datetime


# ─────────────────────────────────────────────
# KULLANICI (AUTH)
# ─────────────────────────────────────────────

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    role: str
    created_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)

class UserRoleUpdate(BaseModel):
    """Kullanıcı rolünü güncellemek için (Admin, Hafta 13)"""
    role: str  # standard | premium | business | admin

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    email: Optional[EmailStr] = None


# ─────────────────────────────────────────────
# DESTİNASYON (HAFTA 5-6)
# ─────────────────────────────────────────────

class DestinationBase(BaseModel):
    name: str
    address: str
    description: Optional[str] = None
    category: str
    ticket_price: Optional[float] = None
    vr_image_url: Optional[str] = None
    opening_hours: Optional[str] = None

class DestinationCreate(DestinationBase):
    latitude: float
    longitude: float

class Destination(DestinationBase):
    id: int
    average_rating: float = 0.0
    is_premium: bool = False
    model_config = ConfigDict(from_attributes=True)

class DestinationWithCoords(Destination):
    """Koordinatları da içeren destinasyon (harita listeleme için)"""
    latitude: Optional[float] = None
    longitude: Optional[float] = None


# ─────────────────────────────────────────────
# YORUM (HAFTA 6)
# ─────────────────────────────────────────────

class ReviewBase(BaseModel):
    rating: int
    comment: Optional[str] = None

class ReviewCreate(ReviewBase):
    destination_id: int

class Review(ReviewBase):
    id: int
    user_id: int
    destination_id: int
    created_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────
# HAFTA 6: YAKINLIK SORGUSU
# ─────────────────────────────────────────────

class NearbyQuery(BaseModel):
    """Kullanıcıya yakın mekanları bulmak için POST body"""
    latitude: float
    longitude: float
    radius_km: float = 5.0
    category: Optional[str] = None


# ─────────────────────────────────────────────
# HAFTA 7: GERÇEK ZAMANLI DOLULUK (WebSocket)
# ─────────────────────────────────────────────

class OccupancyCreate(BaseModel):
    """Doluluk verisi güncellemek için (IoT/admin tarafından gönderilir)"""
    occupancy_rate: float       # 0.0 - 1.0
    visitor_count: Optional[int] = None
    ticket_available: bool = True

class OccupancyResponse(OccupancyCreate):
    id: int
    destination_id: int
    timestamp: datetime.datetime
    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────
# HAFTA 9: AI KALABALIK TAHMİN
# ─────────────────────────────────────────────

class PredictionRequest(BaseModel):
    """Tahmin isteği: hangi saat ve gün için tahmin yapılsın"""
    hour: int           # 0-23
    day_of_week: int    # 0=Pazartesi, 6=Pazar
    is_holiday: bool = False

class PredictionResponse(BaseModel):
    destination_id: int
    predicted_occupancy: float      # 0.0 - 1.0
    crowd_level: str                # "Boş" | "Normal" | "Yoğun" | "Çok Yoğun"
    best_visit_hours: List[int]     # En sakin saatler
    confidence: str                 # "Yüksek" | "Orta" | "Düşük"
    data_points_used: int


# ─────────────────────────────────────────────
# HAFTA 10: AKILLI REHBER & SSS
# ─────────────────────────────────────────────

class FAQCreate(BaseModel):
    question: str
    answer: str
    keywords: Optional[str] = None      # "müze,bilet,fiyat" şeklinde virgüllü
    category: Optional[str] = None
    destination_id: Optional[int] = None

class FAQResponse(FAQCreate):
    id: int
    created_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)

class FAQSearchRequest(BaseModel):
    """NLP anahtar kelime arama isteği"""
    query: str

class FAQSearchResponse(BaseModel):
    query: str
    results: List[FAQResponse]
    matched_keywords: List[str]

class RecommendationRequest(BaseModel):
    """Kişiselleştirilmiş öneri isteği"""
    interests: List[str]        # ["müze", "tarihi", "doğa"]
    max_results: int = 5

class RecommendationResponse(BaseModel):
    destination_id: int
    name: str
    category: str
    average_rating: float
    match_score: float          # 0.0 - 1.0, kullanıcı ilgi alanıyla uyuşma oranı
    reason: str                 # Neden önerildiğinin açıklaması


# ─────────────────────────────────────────────
# HAFTA 12: SOSYAL SİSTEM & ARKADAŞ İNDİRİM
# ─────────────────────────────────────────────

class FriendRequestCreate(BaseModel):
    addressee_id: int

class FriendshipResponse(BaseModel):
    id: int
    requester_id: int
    addressee_id: int
    status: str
    created_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)

class DiscountCheckRequest(BaseModel):
    """İndirim hakkı kontrolü: destination_id ile birlikte bilet alınacak"""
    destination_id: Optional[int] = None

class DiscountCheckResponse(BaseModel):
    eligible: bool
    reason: str
    friend_count: int
    coupon_code: Optional[str] = None   # Hak kazanıldıysa kupon kodu

class CouponResponse(BaseModel):
    id: int
    code: str
    discount_percent: float
    is_used: bool
    expires_at: datetime.datetime
    created_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────
# HAFTA 13: ANALİTİK PANEL & PREMİUM MODEL
# ─────────────────────────────────────────────

class DestinationStats(BaseModel):
    """İşletme sahibine gösterilen destinasyon istatistikleri"""
    destination_id: int
    destination_name: str
    total_reviews: int
    average_rating: float
    total_occupancy_records: int
    average_occupancy_rate: float
    peak_hour: Optional[int]            # En yoğun saat
    busiest_day: Optional[str]          # En yoğun gün adı
    ticket_availability_rate: float     # Bilet müsaitlik oranı

class DashboardResponse(BaseModel):
    """İşletme sahibi dashboard özeti"""
    owner_email: str
    total_destinations: int
    premium_destinations: int
    overall_average_rating: float
    total_reviews: int
    destinations: List[DestinationStats]
