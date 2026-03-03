from pydantic import BaseModel, EmailStr, ConfigDict
from typing import List, Optional
import datetime


class UserBase(BaseModel):
    """ Kullanıcı için temel kalıp (Base Schema) """
    email: EmailStr
    full_name: Optional[str] = None

class UserCreate(UserBase):
    """ Yeni kullanıcı oluştururken gereken kalıp """
    password: str

class User(UserBase):
    """ Veritabanından okurken (API'den döndürürken) kullanılacak kalıp """
    id: int
    created_at: datetime.datetime 
    
    
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    """ /login endpoint'inden döndürülecek kalıp """
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    """ Token'ın (giriş kartının) içinde saklanan veri kalıbı """
    email: Optional[EmailStr] = None



class DestinationBase(BaseModel):
    """
    Destinasyon için temel veri kalıbı.
    Hem oluşturma hem de okuma için ortak alanlar.
    """
    name: str
    address: str
    description: Optional[str] = None
    category: str
    ticket_price: Optional[float] = None
    vr_image_url: Optional[str] = None
    opening_hours: Optional[str] = None 

class DestinationCreate(DestinationBase):
    """
    Yeni bir destinasyon oluştururken API'ye gelmesi gereken
    ekstra veriler (örn: enlem, boylam).
    """
    latitude: float 
    longitude: float 

class Destination(DestinationBase):
    """
    API'den kullanıcıya bir destinasyon döndürürken kullanılacak kalıp.
    (örn: veritabanından okurken)
    """
    id: int
    
    model_config = ConfigDict(from_attributes=True)



class ReviewBase(BaseModel):
    rating: int 
    comment: Optional[str] = None

class ReviewCreate(ReviewBase):
    """ Yorum oluştururken kullanılacak kalıp """
    destination_id: int

class Review(ReviewBase):
    """ Yorumu API'den döndürürken kullanılacak kalıp """
    id: int
    user_id: int
    destination_id: int
    created_at: datetime.datetime 
    model_config = ConfigDict(from_attributes=True)