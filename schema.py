from typing import Optional
from pydantic import BaseModel, Field


class BaseResponse(BaseModel):
    success: bool
    message: str


class User(BaseModel):
    id: str
    created_at: str
    updated_at: str
    telegram_user_id: int
    telegram_username: str
    first_name: str
    last_name: str


class RegisterUserPayload(BaseModel):
    telegram_user_id: int
    telegram_username: str
    first_name: str
    last_name: str


class RegisterUserResponse(BaseResponse):
    user: Optional[User] = Field(default=None, description="User object if registered")


class GetUserPayload(BaseModel):
    telegram_user_id: int


class GetUserResponse(BaseResponse):
    user: Optional[User] = Field(default=None, description="User object if found")
