from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry 
import datetime


from .database import Base



class User(Base):
    """
    Kullanıcı bilgilerini tutar (Kullanıcı Kayıt Defteri Şablonu).
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.UTC))
    
   
    reviews = relationship("Review", back_populates="owner")

class Destination(Base):
    """
    Turistik yerlerin ana bilgilerini tutar (Gidilecek Yer Defteri Şablonu).
    """
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
    
    # İlişkiler: Bir destinasyonun...
    reviews = relationship("Review", back_populates="destination") # ...birden fazla yorumu olabilir
    activities = relationship("Activity", back_populates="destination") # ...birden fazla etkinliği olabilir
    discounts = relationship("Discount", back_populates="destination") # ...birden fazla indirimi olabilir

class Activity(Base):
    """
    Etkinlik/bilet bilgilerini tutar (Etkinlik Defteri Şablonu).
    """
    __tablename__ = "activities"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    price = Column(Float)
    description = Column(String)
    is_available = Column(Boolean, default=True) # Bilet mevcut mu? (Hafta 7'de kullanılacak)
    
    destination_id = Column(Integer, ForeignKey("destinations.id"))
    destination = relationship("Destination", back_populates="activities")

class Review(Base):
    """
    Yorum ve puanları tutar (Yorum Defteri Şablonu).
    """
    __tablename__ = "reviews"
    
    id = Column(Integer, primary_key=True, index=True)
    rating = Column(Integer, index=True) # (1-5 arası)
    comment = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.UTC))
    
    destination_id = Column(Integer, ForeignKey("destinations.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    
    destination = relationship("Destination", back_populates="reviews")
    owner = relationship("User", back_populates="reviews")

class Discount(Base):
    """
    İndirim/kampanyaları tutar (İndirim Defteri Şablonu).
    """
    __tablename__ = "discounts"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    description = Column(String)
    expiry_date = Column(DateTime)
    
    destination_id = Column(Integer, ForeignKey("destinations.id"))
    destination = relationship("Destination", back_populates="discounts")
