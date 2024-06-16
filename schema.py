from datetime import datetime
from typing import List, Optional
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


class FoodItemBase(BaseModel):
    name: str
    description: str
    category: str
    storage_instructions: str
    quantity: float
    unit: str
    expiry_date: Optional[datetime] = Field(default=None)
    shelf_life_days: Optional[int] = Field(default=None)
    reminder_date: datetime
    bounding_box: Optional[dict] = Field(default=None)

class FoodItemCreate(FoodItemBase):
    image_url: str

class FoodItemUpdate(BaseModel):
    id: str
    name: str
    description: str
    category: str
    storage_instructions: str
    quantity: int
    unit: str
    expiry_date: Optional[datetime] = Field(default=None)
    shelf_life_days: Optional[int] = Field(default=None)
    consumed: bool
    discarded: bool


class FoodItemConsumedDiscarded(BaseModel):
    id: str
    consumed: bool
    discarded: bool


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


class CreateFoodItemPayload(BaseModel):
    telegram_user_id: int
    image_url: str
    food_items: List[FoodItemBase] = Field(
        default=[], description="List of food item objects"
    )


class UpdateFoodItemPayload(BaseModel):
    telegram_user_id: int
    food_items: List[FoodItemUpdate] = Field(
        default=[], description="List of update food item objects, restricted to editable fields only"
    )

class ConsumedDiscardedFoodItemPayload(BaseModel):
    telegram_user_id: int
    food_items: List[FoodItemConsumedDiscarded] = Field(
        default=[], description="List of update food item objects, restricted to consumed and discarded fields only"
    )


class DeleteFoodItemPayload(BaseModel):
    telegram_user_id: int
    food_items_id: List[int] = Field(
        default=[], description="List of food item id objects"
    )


class FoodItemDetails(BaseModel):
    name: str
    description: str
    category: str
    storage_instructions: str
    quantity: float
    unit: str
    expiry_date: Optional[datetime] = Field(default=None)
    shelf_life_days: Optional[int] = Field(default=None)
    reminder_date: datetime
    user_id: str
    image_url: Optional[str]
    consumed: bool
    discarded: bool


class FoodItemResponse(FoodItemDetails):
    id: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class ProcessImageResponse(BaseResponse):
    processed_message: str = Field(
        default="", description="message content if processed successfully"
    )


class CreateFoodItemResponse(BaseResponse):
    food_items: List[FoodItemResponse] = Field(
        default=[], description="Food item objects if created successfully"
    )


class ReadFoodItemResponse(BaseResponse):
    food_items: List[FoodItemResponse] = Field(
        default=[], description="Food item objects if read successfully"
    )

class GroupReadFoodItemResponse(BaseResponse):
    telegram_user_id: int
    food_items: List[FoodItemResponse] = Field(
        default=[], description="Food item objects if read successfully"
    )

class UpdateFoodItemResponse(BaseResponse):
    food_items_updated_success: List[FoodItemResponse] = Field(
        default=[], description="Food item objects if updated successfully"
    )
    food_items_updated_failed: List[FoodItemUpdate] = Field(
        default=[], description="Food item objects if updated failed"
    )


class DeleteFoodItemResponse(BaseResponse):
    food_items_id_deleted_failed: List[int] = Field(
        default=[], description="Food item objects if deleted successfully"
    )
