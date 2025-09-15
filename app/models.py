from sqlalchemy import Column, Integer, String, Boolean, BigInteger, ForeignKey, Text, TIMESTAMP
from sqlalchemy.orm import relationship

from app.db import Base


class Creator(Base):
    __tablename__ = "creators"

    id = Column(Integer, primary_key=True)
    handle = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    source_url = Column(String, nullable=False)
    license_type = Column(String, nullable=False)
    post_channel_id = Column(String, nullable=False)
    brand_preset = Column(String, nullable=False, default="default")
    max_daily = Column(Integer, nullable=False, default=8)
    shorts_only = Column(Boolean, nullable=False, default=True)
    enabled = Column(Boolean, nullable=False, default=True)

    videos = relationship("Video", back_populates="creator")


class Video(Base):
    __tablename__ = "videos"

    id = Column(BigInteger, primary_key=True)
    creator_id = Column(Integer, ForeignKey("creators.id"))
    source_id = Column(String, nullable=False)
    duration_s = Column(Integer)
    transcript_url = Column(String)
    status = Column(String, nullable=False, default="queued")
    created_at = Column(TIMESTAMP)

    creator = relationship("Creator", back_populates="videos")
    clips = relationship("Clip", back_populates="video")


class Clip(Base):
    __tablename__ = "clips"

    id = Column(BigInteger, primary_key=True)
    video_id = Column(BigInteger, ForeignKey("videos.id"))
    start_s = Column(Integer, nullable=False)
    end_s = Column(Integer, nullable=False)
    transcript_snippet = Column(Text)
    local_path = Column(String)
    s3_key = Column(String)
    status = Column(String, nullable=False, default="rendered")
    claim_status = Column(String, default="unknown")
    public_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP)

    video = relationship("Video", back_populates="clips")
    uploads = relationship("Upload", back_populates="clip")


class Upload(Base):
    __tablename__ = "uploads"

    id = Column(BigInteger, primary_key=True)
    clip_id = Column(BigInteger, ForeignKey("clips.id"))
    platform = Column(String, nullable=False, default="youtube")
    remote_video_id = Column(String)
    visibility = Column(String, nullable=False, default="unlisted")
    scheduled_for = Column(TIMESTAMP)
    error = Column(Text)

    clip = relationship("Clip", back_populates="uploads")
