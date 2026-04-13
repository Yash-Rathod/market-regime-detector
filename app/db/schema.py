from sqlalchemy import (
    create_engine, Column, String, Float,
    DateTime, Integer, Index, text
)
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()
engine = create_engine(os.getenv("DATABASE_URL"), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


class OHLCVRecord(Base):
    __tablename__ = "ohlcv"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    ticker    = Column(String(20), nullable=False)
    date      = Column(DateTime, nullable=False)
    open      = Column(Float)
    high      = Column(Float)
    low       = Column(Float)
    close     = Column(Float)
    volume    = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_ohlcv_ticker_date", "ticker", "date", unique=True),
    )


class FeatureRecord(Base):
    __tablename__ = "features"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    ticker         = Column(String(20), nullable=False)
    date           = Column(DateTime, nullable=False)
    rsi_14         = Column(Float)
    bb_width       = Column(Float)    # Bollinger Band width
    volatility_20  = Column(Float)    # 20-day rolling std
    momentum_10    = Column(Float)    # 10-day price momentum
    adx_14         = Column(Float)    # Average Directional Index
    volume_ratio   = Column(Float)    # current vol / 20d avg vol
    regime_label   = Column(String(10))  # BULL / BEAR / SIDEWAYS
    created_at     = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_features_ticker_date", "ticker", "date", unique=True),
    )


class ModelMetadata(Base):
    __tablename__ = "model_metadata"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    version     = Column(String(50), nullable=False)
    accuracy    = Column(Float)
    f1_score    = Column(Float)
    trained_at  = Column(DateTime, default=datetime.utcnow)
    is_active   = Column(Integer, default=0)  # 1 = currently serving


def init_db():
    Base.metadata.create_all(bind=engine)
    print("Database tables created.")


if __name__ == "__main__":
    init_db()