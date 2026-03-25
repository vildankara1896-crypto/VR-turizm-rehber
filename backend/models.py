from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
import datetime

from .database import Base


class User(Base):
    """Kullanıcı bilgilerini tutar."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    role = Column(String, default="standard")  # standard, premium, business, admin
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.UTC))

    reviews = relationship("Review", back_populates="owner")
    sent_friendships = relationship(
        "Friendship", foreign_keys="Friendship.requester_id", back_populates="requester"
    )
    received_friendships = relationship(
        "Friendship", foreign_keys="Friendship.addressee_id", back_populates="addressee"
    )
    coupons = relationship("Coupon", back_populates="owner")


class Destination(Base):
    """Turistik yerlerin ana bilgilerini tutar."""
    __tablename__ = "destinations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    address = Column(String)
    description = Column(String)
    category = Column(String, index=True)
    location = Column(Geometry('POINT'))
    vr_image_url = Column(String)
    ticket_price = Column(Float)
    opening_hours = Column(String)
    average_rating = Column(Float, default=0.0)
    is_premium = Column(Boolean, default=False)  # Premium işletme öne çıkarma (Hafta 13)

    reviews = relationship("Review", back_populates="destination")
    activities = relationship("Activity", back_populates="destination")
    discounts = relationship("Discount", back_populates="destination")
    occupancy_logs = relationship("OccupancyLog", back_populates="destination")


class Activity(Base):
    """Etkinlik/bilet bilgilerini tutar."""
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    price = Column(Float)
    description = Column(String)
    is_available = Column(Boolean, default=True)

    destination_id = Column(Integer, ForeignKey("destinations.id"))
    destination = relationship("Destination", back_populates="activities")


class Review(Base):
    """Yorum ve puanları tutar."""
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    rating = Column(Integer, index=True)
    comment = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.UTC))

    destination_id = Column(Integer, ForeignKey("destinations.id"))
    user_id = Column(Integer, ForeignKey("users.id"))

    destination = relationship("Destination", back_populates="reviews")
    owner = relationship("User", back_populates="reviews")


class Discount(Base):
    """İndirim/kampanyaları tutar."""
    __tablename__ = "discounts"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    description = Column(String)
    expiry_date = Column(DateTime)

    destination_id = Column(Integer, ForeignKey("destinations.id"))
    destination = relationship("Destination", back_populates="discounts")


# --- HAFTA 7: WebSocket Gerçek Zamanlı Veri ---

class OccupancyLog(Base):
    """
    Anlık doluluk verilerini tutar.
    WebSocket yayını (Hafta 7) ve AI eğitimi (Hafta 9) için kullanılır.
    """
    __tablename__ = "occupancy_logs"

    id = Column(Integer, primary_key=True, index=True)
    destination_id = Column(Integer, ForeignKey("destinations.id"))
    occupancy_rate = Column(Float)       # 0.0 (boş) ile 1.0 (tam dolu) arası
    visitor_count = Column(Integer, nullable=True)
    ticket_available = Column(Boolean, default=True)
    timestamp = Column(DateTime, default=datetime.datetime.now(datetime.UTC), index=True)

    destination = relationship("Destination", back_populates="occupancy_logs")


# --- HAFTA 10: Akıllı Rehber ---

class FAQ(Base):
    """
    Sıkça Sorulan Sorular veri tabanı.
    NLP anahtar kelime eşleştirmesi için 'keywords' alanı kullanılır.
    """
    __tablename__ = "faqs"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(String)
    answer = Column(Text)
    keywords = Column(String)       # virgülle ayrılmış anahtar kelimeler
    category = Column(String, index=True, nullable=True)
    destination_id = Column(Integer, ForeignKey("destinations.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.UTC))


# --- HAFTA 12: Sosyal Sistem & Arkadaş İndirim ---

class Friendship(Base):
    """
    Kullanıcılar arası arkadaşlık ilişkilerini tutar.
    İndirim koşulu: iki onaylı arkadaşın birlikte bilet alması.
    """
    __tablename__ = "friendships"

    id = Column(Integer, primary_key=True, index=True)
    requester_id = Column(Integer, ForeignKey("users.id"))
    addressee_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="pending")  # pending, accepted, rejected
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.UTC))

    requester = relationship("User", foreign_keys=[requester_id], back_populates="sent_friendships")
    addressee = relationship("User", foreign_keys=[addressee_id], back_populates="received_friendships")


class Coupon(Base):
    """
    Arkadaş indirimi sonucu otomatik üretilen kuponları tutar.
    %10 indirim kodu; koşul: 2+ onaylı arkadaşın varlığı.
    """
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    discount_percent = Column(Float, default=10.0)
    user_id = Column(Integer, ForeignKey("users.id"))
    destination_id = Column(Integer, ForeignKey("destinations.id"), nullable=True)
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.UTC))

    owner = relationship("User", back_populates="coupons")
