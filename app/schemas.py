from pydantic import BaseModel
from typing import Optional


class CreatorIn(BaseModel):
    handle: str
    platform: str
    source_url: str
    license_type: str
    post_channel_id: str
    brand_preset: Optional[str] = "default"
    max_daily: Optional[int] = 8
    shorts_only: Optional[bool] = True
    enabled: Optional[bool] = True


class CreatorOut(CreatorIn):
    id: int

    class Config:
        from_attributes = True
