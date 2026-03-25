"""
HAFTA 12: Sosyal Sistem ve Arkadaş İndirim Mekanizması
──────────────────────────────────────────────────────
Vildan KARA - Backend Geliştirici

İş Kuralları:
- Kullanıcılar birbirine arkadaşlık isteği gönderebilir.
- İstek onaylanınca "accepted" statüsüne geçer.
- 2 veya daha fazla onaylı arkadaşı olan kullanıcı %10 indirim kuponu hakkı kazanır.
- Kupon kodu otomatik üretilir ve 30 gün geçerlidir.
- Her kupon yalnızca bir kez kullanılabilir.
- Backend, indirim uygulanabilirliğini her adımda kontrol eder.
"""

import uuid
import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from .. import models, schemas, database, security

router = APIRouter(
    prefix="/api/v1/social",
    tags=["Sosyal Sistem & İndirim (Hafta 12)"]
)

DISCOUNT_PERCENT = 10.0
COUPON_VALIDITY_DAYS = 30
MIN_FRIENDS_FOR_DISCOUNT = 2


# ─────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────

def _get_accepted_friend_count(user_id: int, db: Session) -> int:
    """Kullanıcının onaylı arkadaş sayısını döndürür."""
    count = db.query(models.Friendship).filter(
        or_(
            and_(models.Friendship.requester_id == user_id, models.Friendship.status == "accepted"),
            and_(models.Friendship.addressee_id == user_id, models.Friendship.status == "accepted"),
        )
    ).count()
    return count


def _get_friendship(user_id: int, other_id: int, db: Session) -> models.Friendship | None:
    """İki kullanıcı arasındaki arkadaşlık kaydını döndürür (varsa)."""
    return db.query(models.Friendship).filter(
        or_(
            and_(models.Friendship.requester_id == user_id, models.Friendship.addressee_id == other_id),
            and_(models.Friendship.requester_id == other_id, models.Friendship.addressee_id == user_id),
        )
    ).first()


def _generate_coupon_code() -> str:
    """Benzersiz indirim kuponu kodu üretir. Örn: VR-A3F9-2B7C"""
    raw = uuid.uuid4().hex.upper()
    return f"VR-{raw[:4]}-{raw[4:8]}"


# ─────────────────────────────────────────────
# ARKADAŞ İSTEKLERİ
# ─────────────────────────────────────────────

@router.post("/friends/request", response_model=schemas.FriendshipResponse, status_code=status.HTTP_201_CREATED)
def send_friend_request(
    request: schemas.FriendRequestCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.get_current_active_user)
):
    """
    Başka bir kullanıcıya arkadaşlık isteği gönderir.
    Aynı çift için birden fazla istek oluşturulamaz.
    """
    if request.addressee_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kendinize arkadaşlık isteği gönderemezsiniz."
        )

    # Karşı kullanıcı var mı?
    addressee = db.query(models.User).filter(models.User.id == request.addressee_id).first()
    if not addressee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı.")

    # Zaten arkadaşlık kaydı var mı?
    existing = _get_friendship(current_user.id, request.addressee_id, db)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bu kullanıcıyla zaten bir arkadaşlık kaydı var (durum: {existing.status})."
        )

    friendship = models.Friendship(
        requester_id=current_user.id,
        addressee_id=request.addressee_id,
        status="pending",
    )
    db.add(friendship)
    db.commit()
    db.refresh(friendship)
    return friendship


@router.put("/friends/{friendship_id}/accept", response_model=schemas.FriendshipResponse)
def accept_friend_request(
    friendship_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.get_current_active_user)
):
    """Gelen arkadaşlık isteğini kabul eder. (Sadece isteği alan kullanıcı kabul edebilir)"""
    friendship = db.query(models.Friendship).filter(models.Friendship.id == friendship_id).first()

    if not friendship:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arkadaşlık isteği bulunamadı.")

    if friendship.addressee_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu isteği yalnızca alıcı kabul edebilir."
        )

    if friendship.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bu istek zaten işleme alındı (durum: {friendship.status})."
        )

    friendship.status = "accepted"
    db.commit()
    db.refresh(friendship)
    return friendship


@router.put("/friends/{friendship_id}/reject", response_model=schemas.FriendshipResponse)
def reject_friend_request(
    friendship_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.get_current_active_user)
):
    """Gelen arkadaşlık isteğini reddeder."""
    friendship = db.query(models.Friendship).filter(models.Friendship.id == friendship_id).first()

    if not friendship:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arkadaşlık isteği bulunamadı.")

    if friendship.addressee_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu isteği yalnızca alıcı reddedebilir.")

    friendship.status = "rejected"
    db.commit()
    db.refresh(friendship)
    return friendship


@router.get("/friends", response_model=list[schemas.FriendshipResponse])
def list_friends(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.get_current_active_user)
):
    """Kullanıcının tüm arkadaşlık kayıtlarını listeler (bekleyen + onaylı)."""
    friendships = db.query(models.Friendship).filter(
        or_(
            models.Friendship.requester_id == current_user.id,
            models.Friendship.addressee_id == current_user.id,
        )
    ).order_by(models.Friendship.created_at.desc()).all()
    return friendships


@router.get("/friends/accepted", response_model=list[schemas.FriendshipResponse])
def list_accepted_friends(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.get_current_active_user)
):
    """Yalnızca onaylı arkadaşları listeler."""
    friendships = db.query(models.Friendship).filter(
        or_(
            and_(models.Friendship.requester_id == current_user.id, models.Friendship.status == "accepted"),
            and_(models.Friendship.addressee_id == current_user.id, models.Friendship.status == "accepted"),
        )
    ).all()
    return friendships


# ─────────────────────────────────────────────
# İNDİRİM MEKANİZMASI (Hafta 12 Ana Özelliği)
# ─────────────────────────────────────────────

@router.post("/discount/check", response_model=schemas.DiscountCheckResponse)
def check_discount_eligibility(
    request: schemas.DiscountCheckRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.get_current_active_user)
):
    """
    Kullanıcının %10 arkadaş indiriminden yararlanıp yararlanamayacağını kontrol eder.

    Koşul: Kullanıcının 2 veya daha fazla onaylı arkadaşı olmalı.
    Hak kazanıldığında otomatik olarak 30 günlük kupon kodu üretilir.
    """
    friend_count = _get_accepted_friend_count(current_user.id, db)

    if friend_count < MIN_FRIENDS_FOR_DISCOUNT:
        return schemas.DiscountCheckResponse(
            eligible=False,
            reason=(
                f"İndirim için en az {MIN_FRIENDS_FOR_DISCOUNT} onaylı arkadaşınız olmalıdır. "
                f"Şu an {friend_count} onaylı arkadaşınız var."
            ),
            friend_count=friend_count,
            coupon_code=None,
        )

    # Kullanılmamış aktif kupon var mı?
    now = datetime.datetime.now(datetime.UTC)
    existing_coupon = db.query(models.Coupon).filter(
        models.Coupon.user_id == current_user.id,
        models.Coupon.is_used == False,
        models.Coupon.expires_at > now,
        models.Coupon.destination_id == request.destination_id if request.destination_id else True,
    ).first()

    if existing_coupon:
        return schemas.DiscountCheckResponse(
            eligible=True,
            reason="Zaten aktif bir indirim kuponunuz var.",
            friend_count=friend_count,
            coupon_code=existing_coupon.code,
        )

    # Yeni kupon oluştur
    coupon_code = _generate_coupon_code()
    expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=COUPON_VALIDITY_DAYS)

    new_coupon = models.Coupon(
        code=coupon_code,
        discount_percent=DISCOUNT_PERCENT,
        user_id=current_user.id,
        destination_id=request.destination_id,
        is_used=False,
        expires_at=expires_at,
    )
    db.add(new_coupon)
    db.commit()

    return schemas.DiscountCheckResponse(
        eligible=True,
        reason=(
            f"Tebrikler! {friend_count} onaylı arkadaşınız var. "
            f"%{int(DISCOUNT_PERCENT)} indirim kuponunuz oluşturuldu ({COUPON_VALIDITY_DAYS} gün geçerli)."
        ),
        friend_count=friend_count,
        coupon_code=coupon_code,
    )


@router.post("/discount/apply/{coupon_code}", response_model=schemas.CouponResponse)
def apply_coupon(
    coupon_code: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.get_current_active_user)
):
    """
    Kuponu kullanıldı olarak işaretler.
    (Bilet satın alım sürecinde çağrılır, ödeme entegrasyonuyla birlikte çalışır)
    """
    now = datetime.datetime.now(datetime.UTC)
    coupon = db.query(models.Coupon).filter(
        models.Coupon.code == coupon_code.upper(),
        models.Coupon.user_id == current_user.id,
    ).first()

    if not coupon:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kupon bulunamadı.")

    if coupon.is_used:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu kupon zaten kullanılmış.")

    if coupon.expires_at < now.replace(tzinfo=None):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu kuponun süresi dolmuş.")

    coupon.is_used = True
    db.commit()
    db.refresh(coupon)
    return coupon


@router.get("/discount/my-coupons", response_model=list[schemas.CouponResponse])
def list_my_coupons(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.get_current_active_user)
):
    """Kullanıcının tüm kuponlarını listeler."""
    return db.query(models.Coupon).filter(
        models.Coupon.user_id == current_user.id
    ).order_by(models.Coupon.created_at.desc()).all()
