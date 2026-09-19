from typing import Literal

from pydantic import BaseModel, Field

# Cấu trúc dữ liệu Frontend gửi lên
class ChatRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    user_id: str = Field(default="default", min_length=1, max_length=100)
    response_mode: str = Field(default="auto", min_length=1, max_length=20, pattern="^(auto|fast|deep)$")
    input_source: Literal["text", "microphone"] = "text"

# Cấu trúc dữ liệu Backend trả về cho Frontend
class ChatResponse(BaseModel):
    reply_vi: str         # Dành cho phụ đề tiếng Việt
    motion: str          # Dành cho Live2D (motion)
    expression: str      # Dành cho Live2D (expression)
    response_mode: str = Field(default="fast")
    due_reminders: list[dict] = Field(default_factory=list)
    timing: dict = Field(default_factory=dict)
    search: dict | None = None
