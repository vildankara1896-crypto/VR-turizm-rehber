from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta

# Kendi oluşturduğumuz dosyalardan import yapıyoruz
from .. import database, models, schemas, security

# Bu dosyadaki tüm adreslerin /api/v1/auth ile başlamasını sağlar
router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"] # FastAPI dokümantasyonunda gruplama yapar
)

# --- YARDIMCI BAĞIMLILIK (Dependency) ---

def get_current_user(
    db: Session = Depends(database.get_db), 
    token: str = Depends(security.oauth2_scheme)
) -> models.User:
    """
    Kullanıcıdan gelen token'ı (giriş kartını) alır,
    doğrular ve veritabanından o kullanıcıyı bulup döndürür.
    Bu fonksiyonu, "giriş yapmayı gerektiren" tüm endpoint'lerde kullanacağız.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Token'ı doğrula
    token_data = security.verify_token(token, credentials_exception)
    
    # Kullanıcıyı veritabanından bul
    user = db.query(models.User).filter(models.User.email == token_data.email).first()
    if user is None:
        raise credentials_exception
    
    return user


# --- API ENDPOINTS (WEB ADRESLERİ) ---

@router.post("/register", response_model=schemas.User)
def register_user(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    """
    Hafta 4 Görevi: Yeni kullanıcı kayıt endpoint'i.
    Gelen 'user' verisi, schemas.UserCreate kalıbına uymalı.
    """
    # 1. Bu e-posta zaten kayıtlı mı diye kontrol et
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # 2. Parolayı hash'le (security.py dosyasındaki fonksiyon ile)
    hashed_password = security.get_password_hash(user.password)
    
    # 3. Yeni kullanıcıyı models.User olarak oluştur ve veritabanına kaydet
    db_user = models.User(
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # 4. response_model=schemas.User sayesinde
    #    parola bilgisi GÖNDERİLMEDEN kullanıcı bilgisi döndürülür.
    return db_user


@router.post("/login", response_model=schemas.Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(database.get_db)
):
    """
    Hafta 4 Görevi: Kullanıcı giriş endpoint'i.
    FastAPI'nin özel OAuth2PasswordRequestForm'unu kullanır.
    Bu form, 'username' (bizim için email) ve 'password' alanlarını içerir.
    """
    # 1. Kullanıcıyı e-postadan (form_data.username) bul
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    
    # 2. Kullanıcı yoksa VEYA şifre yanlışsa hata ver
    # (security.py'deki verify_password fonksiyonunu kullan)
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # 3. Access ve Refresh token oluştur (security.py fonksiyonları ile)
    # Token'ın içine kullanıcının kim olduğunu belirten bir bilgi (sub) koyarız
    access_token = security.create_access_token(
        data={"sub": user.email}
    )
    
    refresh_token = security.create_refresh_token(
        data={"sub": user.email}
    )
    
    # 4. schemas.Token kalıbında token'ları döndür
    return {
        "access_token": access_token, 
        "refresh_token": refresh_token, 
        "token_type": "bearer"
    }

@router.get("/users/me", response_model=schemas.User)
def read_users_me(current_user: models.User = Depends(get_current_user)):
    """
    Hafta 4 Görevi: Korumalı profilim endpoint'i.
    Bu endpoint, sadece geçerli bir token (giriş kartı) gönderen
    kullanıcılar için çalışır.
    'current_user' parametresi, 'get_current_user' bağımlılığı
    sayesinde otomatik olarak token'dan gelen kullanıcı bilgisiyle dolar.
    """
    return current_user

# Hafta 4 Görevi - /token/refresh
@router.post("/token/refresh", response_model=schemas.Token)
def refresh_access_token(
    current_user_email: str = Depends(security.oauth2_scheme), # Bu bir token olmalı
    db: Session = Depends(database.get_db)
):
    """
    Hafta 4 Görevi: Access token'ı yenilemek için kullanılır.
    Burada 'security.oauth2_scheme'i geçici olarak kullandık,
    normalde bir 'Refresh Token' şeması gerekir, ancak planı takip edelim.
    Bu, 'Refresh Token'ı 'Bearer' olarak göndermenizi bekler.
    """
    # Token'ı doğrula ve kullanıcı e-postasını al
    # Aslında, 'get_current_user_from_refresh_token' gibi ayrı bir
    # dependency daha güvenli olurdu, ama şimdilik basitleştirelim.
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials for refresh",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token_data = security.verify_token(current_user_email, credentials_exception)
    
    user = db.query(models.User).filter(models.User.email == token_data.email).first()
    
    if user is None:
        raise credentials_exception

    # Yeni bir Access Token oluştur, Refresh Token'ı TEKRAR KULLAN
    new_access_token = security.create_access_token(
        data={"sub": user.email}
    )
    
    # Normalde refresh token da döndürülür
    # Şimdilik, var olan refresh token'ın geçerli olduğunu varsayıyoruz
    # veya yeni bir tane oluşturabiliriz. Planda detay yok, yeni oluşturalım:
    new_refresh_token = security.create_refresh_token(
        data={"sub": user.email}
    )

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token, # Yeni bir refresh token döndürmek daha güvenli
        "token_type": "bearer"
    }
