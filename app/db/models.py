"""SQLAlchemy models for the two tables: text chunks and extracted financial metrics."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, Integer, String, Text, UniqueConstraint, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import get_settings

EMBEDDING_DIM = get_settings().embedding_dim


class Base(DeclarativeBase):
    pass


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company: Mapped[str] = mapped_column(String(32), index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, index=True)
    page: Mapped[int] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))


class FinancialMetric(Base):
    __tablename__ = "financial_metrics"
    # One value per company/year/metric. Each report's current-year column is the source.
    __table_args__ = (UniqueConstraint("company", "fiscal_year", "metric"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company: Mapped[str] = mapped_column(String(32), index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, index=True)
    metric: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))  # e.g. "crore", "percent", "count"
    currency: Mapped[str | None] = mapped_column(String(8))  # e.g. "INR"; None for non-money
    source_page: Mapped[int] = mapped_column(Integer)


def get_engine():
    return create_engine(get_settings().database_url)


def init_db(engine=None) -> None:
    """Enable pgvector and create tables if they don't exist."""
    engine = engine or get_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
