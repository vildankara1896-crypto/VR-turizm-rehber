from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import EmailStr
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer


from . import schemas


from sqlalchemy.orm import Session 
from . import models, database      


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Kullanıcının girdiği 'düz şifre' ile veritabanındaki
    'kıymalı şifre'yi karşılaştırır.
    """
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """
    Gelen düz şifreyi 'kıyma'ya (hash) çevirir.
    """
    return pwd_context.hash(password)


SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30  
REFRESH_TOKEN_EXPIRE_DAYS = 7    


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """
    Kısa ömürlü 'Access Token' (Giriş Kartı) oluşturur.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict, expires_delta: timedelta | None = None):
    """
    Uzun ömürlü 'Refresh Token' (Kart Yenileme Kartı) oluşturur.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str, credentials_exception: HTTPException) -> schemas.TokenData:
    """
    Gelen bir token'ı (giriş kartını) doğrular ve içindeki veriyi
    (örn: kullanıcı e-postası) döndürür.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: EmailStr | None = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        raise credentials_exception
    
    return token_data
    
credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Kimlik bilgileri doğrulanamadı",
    headers={"WWW-Authenticate": "Bearer"},
)



def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    """
    Access token'ı çözer ve token'ın içerdiği e-posta ile veritabanından kullanıcıyı çeker.
    """
  
    try:
     
        token_data = verify_token(token, credentials_exception) 
    except JWTError:
        raise credentials_exception

   
    user = db.query(models.User).filter(models.User.email == token_data.email).first()
    
    if user is None:
        raise credentials_exception
        
    return user

def get_current_active_user(current_user: models.User = Depends(get_current_user)):
    """
    Giriş yapmış (Access Token'ı geçerli) kullanıcıyı döndürür. 
    Destinasyon CRUD'u gibi korumalı endpoint'ler için kullanılır.
    """
   
    return current_user


def get_current_active_user(current_user: models.User = Depends(get_current_user)):
    """
    Giriş yapmış (Access Token'ı geçerli) kullanıcıyı döndürür.
    Bu bağımlılık, çoğu korumalı API endpoint'i için kullanılır.
    """
 
    return current_user