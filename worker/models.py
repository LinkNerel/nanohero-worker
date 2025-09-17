from __future__ import annotations

from enum import Enum
from sqlalchemy import (
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    func,
    Integer,
    String,
    Boolean,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


class UserRole(str, Enum):
    streamer = "streamer"
    advertiser = "advertiser"
    admin = "admin"


class ServingEvent(str, Enum):
    impression = "impression"
    beat = "beat"
    click = "click"


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.streamer)
    email = Column(String(255), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=True)
    twitch_broadcaster_id = Column(String(100), unique=True, nullable=True)
    stripe_account_id = Column(String(255), unique=True, nullable=True)

    campaigns = relationship("Campaign", back_populates="owner")


class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("User", back_populates="campaigns")
    creatives = relationship("Creative", back_populates="campaign")


class Creative(Base):
    __tablename__ = "creatives"
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    creative_url = Column(Text, nullable=False)
    click_url = Column(Text, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    duration_s = Column(Integer, nullable=False, default=15)

    campaign = relationship("Campaign", back_populates="creatives")


class ServingLog(Base):
    __tablename__ = "serving_logs"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    streamer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True)
    creative_id = Column(Integer, ForeignKey("creatives.id"), nullable=True)
    event = Column(SQLEnum(ServingEvent), nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    visible = Column(Boolean, nullable=True)
    viewer_count = Column(Integer, nullable=True)


class Stream(Base):
    __tablename__ = "streams"
    id = Column(Integer, primary_key=True)
    streamer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    viewer_count = Column(Integer, nullable=False, default=0)
