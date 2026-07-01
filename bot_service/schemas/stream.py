from pydantic import BaseModel
from typing import Optional

class CategoryObject(BaseModel):
    id: str
    title: Optional[str] = None
    cover_url: Optional[str] = None
    type: Optional[str] = None
    name: Optional[str] = None  # Alias for title (frontend uses 'name')

class PlatformUpdate(BaseModel):
    title: Optional[str] = None
    category_id: Optional[str] = None
    category: Optional[CategoryObject] = None  # Full category object for VK

class StreamUpdateRequest(BaseModel):
    twitch: Optional[PlatformUpdate] = None
    vk: Optional[PlatformUpdate] = None
