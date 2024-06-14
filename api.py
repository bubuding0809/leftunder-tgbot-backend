import base64
import os
import uuid
from dotenv import load_dotenv
import utils
import json
from pydantic import ValidationError
from supabase import create_client
from typing import List
from schema import (
    CreateFoodItemPayload,
    CreateFoodItemResponse,
    FoodItemResponse,
    GetUserPayload,
    GetUserResponse,
    RegisterUserPayload,
    RegisterUserResponse,
    User,
    FoodItemDetails
)

load_dotenv()
SUPABASE_STORAGE_PUBLIC_URL = os.environ.get("SUPABASE_STORAGE_PUBLIC_URL")


class Api:
    def __init__(self, supabase_url: str, supabase_key: str):
        self.supabase = create_client(supabase_url, supabase_key)

    def get_user(self, payload: GetUserPayload) -> GetUserResponse:
        try:
            response = (
                self.supabase.table("User")
                .select("*")
                .eq("telegram_user_id", payload.telegram_user_id)
                .execute()
            )
        except Exception as e:
            return GetUserResponse(success=False, message=str(e))

        if not response.data:
            return GetUserResponse(success=False, message="User not found")

        try:
            user = User(**response.data[0])
            return GetUserResponse(success=True, message="User found", user=user)
        except ValidationError as e:
            return GetUserResponse(success=False, message=str(e))

    def register_user(self, payload: RegisterUserPayload) -> RegisterUserResponse:
        try:
            response = (
                self.supabase.table("User").insert(payload.model_dump()).execute()
            )
        except Exception as e:
            return RegisterUserResponse(success=False, message=str(e))

        try:
            user = User(**response.data[0])
            return RegisterUserResponse(
                success=True, message="User registered", user=user
            )
        except ValidationError as e:
            return RegisterUserResponse(success=False, message=str(e))

    async def create_food_items(
        self, payload: CreateFoodItemPayload
    ) -> CreateFoodItemResponse:
        user_response = self.get_user(
            GetUserPayload(telegram_user_id=payload.telegram_user_id)
        )
        user = user_response.user
        if user is None:
            return CreateFoodItemResponse(success=False, message="User not found")

        bucket = self.supabase.storage.from_("public-assets")

        food_item_payloads: List[FoodItemDetails] = []
        for item in payload.food_items:
            cropped_image_base64 = utils.crop_and_return_base64_image(payload.image_base64, item.bounding_box)
            image_url = None
            try:
                image_path = f"{uuid.uuid4()}.jpg"
                # Upload the image to the storage bucket
                image_response = bucket.upload(
                    path=image_path,
                    file=base64.b64decode(cropped_image_base64),
                    file_options={"content-type": "image/jpeg"},
                )
                image_key: str = image_response.json()["Key"]
                # Construct public url of the uploaded image
                image_url = f"{SUPABASE_STORAGE_PUBLIC_URL}/{image_key}"
            except Exception as e:
                print("Error uploading image", e)

            food_item_payload_data = {
                "name": item.name,
                "description": item.description,
                "category": item.category,
                "storage_instructions": item.storage_instructions,
                "quantity": item.quantity,
                "unit": item.unit,
                "expiry_date": (
                    item.expiry_date.isoformat() if item.expiry_date else None
                ),
                "shelf_life_days": item.shelf_life_days,
                "reminder_date": item.reminder_date.isoformat(),
                "user_id": user.id,
                "image_url": image_url,
                "consumed": False,
                "discarded": False
            }
            food_item_payloads.append(FoodItemDetails(**food_item_payload_data))

        try:
            response = (
                self.supabase.table("FoodItem").insert(food_item_payloads).execute()
            )
        except Exception as e:
            print("Error creating food items", e)
            return CreateFoodItemResponse(success=False, message=str(e))

        try:
            food_items = [FoodItemResponse(**item) for item in response.data]
            return CreateFoodItemResponse(
                success=True, message="Food item created", food_items=food_items
            )
        except ValidationError as e:
            print("Error parsing food items", e)
            return CreateFoodItemResponse(success=False, message=str(e))