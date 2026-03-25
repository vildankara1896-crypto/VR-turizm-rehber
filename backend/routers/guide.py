"""
HAFTA 10: Akıllı Rehber ve Kişiselleştirilmiş Öneriler
──────────────────────────────────────────────────────
Vildan KARA - Backend Geliştirici

Bu modül iki sistemi içerir:
1. SSS (FAQ) Veri Tabanı: Admin tarafından yönetilen soru-cevap arşivi.
2. NLP Anahtar Kelime Eşleştirmesi: Kullanıcının sorgusunu anahtar kelimelerle eşleştirir.
3. Öneri Algoritması: İlgi alanlarına göre mekanları puanlar ve sıralar.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional

from .. import models, schemas, database, security

router = APIRouter(
    prefix="/api/v1/guide",
    tags=["Akıllı Rehber & SSS (Hafta 10)"]
)


# ─────────────────────────────────────────────
# SSS (FAQ) YÖNETİMİ
# ─────────────────────────────────────────────

@router.post("/faq", response_model=schemas.FAQResponse, status_code=status.HTTP_201_CREATED)
def create_faq(
    faq: schemas.FAQCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.require_role("admin"))
):
    """SSS veri tabanına yeni soru-cevap ekler. (Sadece Admin)"""
    db_faq = models.FAQ(**faq.model_dump())
    db.add(db_faq)
    db.commit()
    db.refresh(db_faq)
    return db_faq


@router.get("/faq", response_model=List[schemas.FAQResponse])
def list_faqs(
    category: Optional[str] = Query(None, description="Kategoriye göre filtrele"),
    destination_id: Optional[int] = Query(None, description="Belirli bir mekana ait SSS"),
    db: Session = Depends(database.get_db)
):
    """Tüm SSS kayıtlarını listeler. Kategori veya mekan filtresi uygulanabilir."""
    query = db.query(models.FAQ)
    if category:
        query = query.filter(models.FAQ.category == category)
    if destination_id:
        query = query.filter(models.FAQ.destination_id == destination_id)
    return query.order_by(models.FAQ.created_at.desc()).all()


@router.get("/faq/{faq_id}", response_model=schemas.FAQResponse)
def get_faq(faq_id: int, db: Session = Depends(database.get_db)):
    """Belirli bir SSS kaydını döndürür."""
    faq = db.query(models.FAQ).filter(models.FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSS kaydı bulunamadı.")
    return faq


# ─────────────────────────────────────────────
# NLP ANAHTAR KELİME EŞLEŞTİRMESİ
# ─────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    """Metni küçük harfe çevirip boşluk ve noktalama ile böler."""
    import re
    tokens = re.findall(r'\w+', text.lower())
    return set(tokens)


def _faq_relevance_score(query_tokens: set[str], faq: models.FAQ) -> tuple[float, list[str]]:
    """
    Bir SSS kaydının sorguyla ne kadar ilgili olduğunu hesaplar.
    Döndürür: (skor 0.0-1.0, eşleşen anahtar kelimeler)
    """
    matched_keywords: list[str] = []
    score = 0.0

    # Anahtar kelime eşleşmesi (en yüksek ağırlık)
    if faq.keywords:
        faq_keywords = {kw.strip().lower() for kw in faq.keywords.split(",")}
        keyword_matches = query_tokens & faq_keywords
        if keyword_matches:
            matched_keywords.extend(keyword_matches)
            score += len(keyword_matches) * 0.5

    # Soru metninde geçiyor mu?
    question_tokens = _tokenize(faq.question)
    q_overlap = query_tokens & question_tokens
    if q_overlap:
        matched_keywords.extend(q_overlap - set(matched_keywords))
        score += len(q_overlap) * 0.3

    # Cevap metninde geçiyor mu?
    answer_tokens = _tokenize(faq.answer)
    a_overlap = query_tokens & answer_tokens
    score += len(a_overlap) * 0.1

    # Normalize (max 1.0)
    max_possible = max(len(query_tokens) * 0.5, 0.5)
    return min(score / max_possible, 1.0), list(set(matched_keywords))


@router.post("/faq/search", response_model=schemas.FAQSearchResponse)
def search_faq(
    request: schemas.FAQSearchRequest,
    db: Session = Depends(database.get_db)
):
    """
    NLP tabanlı SSS arama.
    Kullanıcının sorgusunu anahtar kelimelerle eşleştirerek en alakalı cevapları döndürür.

    Örnek: {"query": "müze bilet fiyatı ne kadar"}
    """
    if len(request.query.strip()) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sorgu en az 2 karakter olmalıdır."
        )

    query_tokens = _tokenize(request.query)
    all_faqs = db.query(models.FAQ).all()

    scored: list[tuple[float, list[str], models.FAQ]] = []
    for faq in all_faqs:
        score, matched = _faq_relevance_score(query_tokens, faq)
        if score > 0:
            scored.append((score, matched, faq))

    # Skora göre sırala
    scored.sort(key=lambda x: x[0], reverse=True)
    top_results = scored[:5]  # En iyi 5 sonuç

    all_matched = list({kw for _, matched, _ in top_results for kw in matched})

    return schemas.FAQSearchResponse(
        query=request.query,
        results=[schemas.FAQResponse.model_validate(faq) for _, _, faq in top_results],
        matched_keywords=all_matched,
    )


# ─────────────────────────────────────────────
# KİŞİSELLEŞTİRİLMİŞ ÖNERİ ALGORİTMASI
# ─────────────────────────────────────────────

# Kategori - ilgi alanı eşleme tablosu
CATEGORY_INTEREST_MAP = {
    "müze":      ["müze", "tarih", "kültür", "sanat", "arkeoloji"],
    "tarihi":    ["tarih", "tarihi", "osmanlı", "antik", "kültür"],
    "doğa":      ["doğa", "park", "orman", "dağ", "yürüyüş", "kamp"],
    "plaj":      ["deniz", "plaj", "yüzme", "tatil", "güneş"],
    "restoran":  ["yemek", "gastronomi", "mutfak", "lezzet", "restoran"],
    "alışveriş": ["alışveriş", "çarşı", "pazar", "moda"],
    "eğlence":   ["eğlence", "gece hayatı", "konser", "festival", "etkinlik"],
    "dini":      ["cami", "kilise", "dini", "ibadet"],
}


def _calculate_match_score(interests: list[str], destination: models.Destination) -> tuple[float, str]:
    """
    Kullanıcının ilgi alanlarının destinasyonla uyuşma oranını hesaplar.
    Döndürür: (skor 0.0-1.0, neden açıklaması)
    """
    interest_tokens = set()
    for interest in interests:
        interest_tokens.update(interest.lower().split())

    score = 0.0
    reasons = []

    # Kategori eşleşmesi (en yüksek ağırlık)
    category_lower = destination.category.lower() if destination.category else ""
    if category_lower in CATEGORY_INTEREST_MAP:
        category_keywords = set(CATEGORY_INTEREST_MAP[category_lower])
        overlap = interest_tokens & category_keywords
        if overlap:
            score += 0.6
            reasons.append(f"{destination.category} kategorisiyle ilgileniyorsunuz")

    # Doğrudan kategori adı eşleşmesi
    for interest in interests:
        if interest.lower() in category_lower or category_lower in interest.lower():
            score += 0.3
            reasons.append(f"'{interest}' ilgi alanınızla eşleşiyor")
            break

    # İsim eşleşmesi
    name_tokens = _tokenize(destination.name) if destination.name else set()
    name_overlap = interest_tokens & name_tokens
    if name_overlap:
        score += 0.1

    # Puan bonusu (yüksek puanlı mekanlar önerilir)
    if destination.average_rating and destination.average_rating >= 4.0:
        score += 0.1
        if destination.average_rating >= 4.5:
            reasons.append("çok yüksek kullanıcı puanı")
        else:
            reasons.append("yüksek kullanıcı puanı")

    reason_text = ", ".join(reasons) if reasons else "Genel öneri"
    return min(score, 1.0), reason_text.capitalize()


@router.post("/recommendations", response_model=List[schemas.RecommendationResponse])
def get_recommendations(
    request: schemas.RecommendationRequest,
    db: Session = Depends(database.get_db)
):
    """
    Kullanıcının ilgi alanlarına göre kişiselleştirilmiş mekan önerileri sunar.

    Örnek istek: {"interests": ["müze", "tarih", "kültür"], "max_results": 5}
    Algoritma: kategori-ilgi eşleşme skoru + ortalama puan bonusu
    """
    if not request.interests:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="En az bir ilgi alanı girilmelidir."
        )

    destinations = db.query(models.Destination).all()

    scored: list[tuple[float, str, models.Destination]] = []
    for dest in destinations:
        score, reason = _calculate_match_score(request.interests, dest)
        if score > 0:
            scored.append((score, reason, dest))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[: request.max_results]

    return [
        schemas.RecommendationResponse(
            destination_id=dest.id,
            name=dest.name,
            category=dest.category,
            average_rating=dest.average_rating or 0.0,
            match_score=round(score, 3),
            reason=reason,
        )
        for score, reason, dest in top
    ]


@router.get("/recommendations/popular", response_model=List[schemas.RecommendationResponse])
def get_popular_destinations(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(database.get_db)
):
    """
    En yüksek puanlı destinasyonları döndürür.
    Belirli ilgi alanı olmayan kullanıcılar için akıllı dashboard başlangıcı.
    """
    top_destinations = db.query(models.Destination).order_by(
        models.Destination.is_premium.desc(),
        models.Destination.average_rating.desc()
    ).limit(limit).all()

    return [
        schemas.RecommendationResponse(
            destination_id=dest.id,
            name=dest.name,
            category=dest.category,
            average_rating=dest.average_rating or 0.0,
            match_score=1.0,
            reason="Popüler ve yüksek puanlı mekan",
        )
        for dest in top_destinations
    ]
