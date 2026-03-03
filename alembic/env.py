import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# --- VILDAN'IN KRİTİK DÜZELTMELERİ (Hafta 3) ---

# 1. Backend klasörünü Python yoluna ekle (models ve database'i bulması için)
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

# 2. Modelleri ve DB URL'sini import et
from backend import models
from backend.database import SQLALCHEMY_DATABASE_URL 

# ORM modellerini Alembic'e tanıt
target_metadata = models.Base.metadata

# --- ALEMBIC TEMEL FONKSİYONLARI ---

def run_migrations_offline() -> None:
    """Modelleri çevrimdışı modda çalıştır (genellikle kullanılmaz)."""
    url = context.config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Modelleri çevrimiçi modda çalıştır (autogenerate için gereklidir)."""
    
    # Vildan'ın Düzeltmesi: sqlalchemy.url'i database.py dosyasındaki Docker URL'si ile değiştir.
    # Bu, 'localhost:5432' hatasını çözer.
    context.config.set_main_option("sqlalchemy.url", SQLALCHEMY_DATABASE_URL)
    
    connectable = engine_from_config(
        context.config.get_section(context.config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

# --- BAŞLANGIÇ NOKTASI ---

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()