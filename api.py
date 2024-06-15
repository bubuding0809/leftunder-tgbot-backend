import base64
from collections import defaultdict
import datetime
import os
import uuid
from dotenv import load_dotenv
import utils
import json
from pydantic import ValidationError
from supabase import create_client
from typing import List
from utils import calculate_reminder_date
from schema import (
    BaseResponse,
    CreateFoodItemPayload,
    UpdateFoodItemPayload,
    DeleteFoodItemPayload,
    CreateFoodItemResponse,
    ReadFoodItemResponse,
    UpdateFoodItemResponse,
    DeleteFoodItemResponse,
    FoodItemResponse,
    GetUserPayload,
    GetUserResponse,
    RegisterUserPayload,
    RegisterUserResponse,
    User,
    FoodItemDetails,
    FoodItemUpdate
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
        
    async def read_food_items_for_user(self, telegram_user_id: str
    ) -> ReadFoodItemResponse:
        user_response: GetUserResponse = self.get_user(
            GetUserPayload(telegram_user_id=telegram_user_id)
        )
        user: User = user_response.user
        if user is None:
            return ReadFoodItemResponse(success=False, message="User not found")

        try:
            response = self.supabase.table("FoodItem").select("*").eq("user_id", user.id).order_by("created_at", ascending=False).execute()
            food_items = [FoodItemResponse(**item) for item in response.data]
            return ReadFoodItemResponse(
                success=True, message="Food items read successfully", food_items=food_items
            )
        except Exception as e:
            print("Error reading food items", e)
            return ReadFoodItemResponse(success=False, message=str(e))

    async def update_food_items(
        self, payload: UpdateFoodItemPayload
    ) -> UpdateFoodItemResponse:
        user_response = self.get_user(
            GetUserPayload(telegram_user_id=payload.telegram_user_id)
        )
        user = user_response.user
        if user is None:
            return UpdateFoodItemResponse(success=False, message="User not found")

        food_items_updated_success: List[FoodItemResponse] = []
        food_items_updated_failed: List[FoodItemUpdate] = []

        food_item_payloads: List[FoodItemUpdate] = []
        for update_item in payload.food_items:
            food_item_id = update_item.get("id")

            updated_data = {
                "name": update_item.name,
                "description": update_item.description,
                "category": update_item.category,
                "storage_instructions": update_item.storage_instructions,
                "quantity": update_item.quantity,
                "unit": update_item.unit,
                "expiry_date": (
                    update_item.expiry_date.isoformat() if update_item.expiry_date else None
                ),
                "shelf_life_days": update_item.shelf_life_days,
                "reminder_date": calculate_reminder_date(update_item).isoformat(),
                "consumed": update_item.consumed,
                "discarded": update_item.discarded
            }
            
            try:
                response = self.supabase.table("FoodItem").update(updated_data).eq("id", food_item_id).execute()
                food_items = [FoodItemResponse(**item) for item in response.data]
                food_items_updated_success.extend(food_items)
            except Exception as e:
                print(f"Error updating food items of id {food_item_id}", e)
                food_items_updated_failed.append(update_item)
                continue

        return UpdateFoodItemResponse(
            success=False if len(food_items_updated_failed) > 0 else True,
            message="Food items updated", 
            food_items_updated_success=food_items_updated_success,
            food_items_updated_failed=food_items_updated_failed
        )
    
    async def delete_food_items_for_user(self, payload: DeleteFoodItemPayload
    ) -> DeleteFoodItemResponse:
        user_response = self.get_user(
            GetUserPayload(telegram_user_id=payload.telegram_user_id)
        )
        user = user_response.user
        if user is None:
            return UpdateFoodItemResponse(success=False, message="User not found")
        
        food_items_id: List[int] = payload.food_items_id

        food_items_id_deleted_failed: List[int] = []
        
        for item_id in food_items_id:
            try:
                response = self.supabase.table("FoodItem").delete().eq("id", item_id).execute()
            except Exception as e:
                    print(f"Error deleting food items of id {item_id}", e)
                    food_items_id_deleted_failed.append(item_id)
                    continue

        return DeleteFoodItemResponse(
            success=False if len(food_items_id_deleted_failed) > 0 else True,
            message="Food items deleted", 
            food_items_id_deleted_failed=food_items_id_deleted_failed
        )   

    async def sync_reminder_date_food_items(self) -> BaseResponse:
        # Get current datetime
        current_datetime = datetime.datetime.now()
        current_datetime_iso = current_datetime.isoformat()
        # new reminder datetime is 23 hours from current datetime
        next_reminder_datetime = current_datetime + datetime.timedelta(hours=23) 
        next_reminder_datetime_iso = next_reminder_datetime.isoformat()

        TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        
        try:
            response = self.supabase.table("FoodItem").update({"reminder_date", next_reminder_datetime_iso}).eq("consumed", False).eq("discarded", False).lt("reminder_date", current_datetime_iso).execute()
            food_items = [FoodItemResponse(**item) for item in response.data]

            grouped_food_items = defaultdict(list)
            for item in food_items:
                grouped_food_items[item.user_id].append(item)
            # Convert the defaultdict to a regular dictionary
            grouped_food_items = dict(grouped_food_items)

            for id_user_table, user_food_items_list in grouped_food_items.items():
                telegram_user_id = self.supabase.table("User").select("telegram_user_id").eq("id", id_user_table).execute()
                #TODO: test the util function and format the telegram message
                utils.send_telegram_message(TELEGRAM_BOT_TOKEN, telegram_user_id, user_food_items_list)

            return BaseResponse(
                success=False,
                message="Sync food items success"
            )
        except Exception as e:
            return BaseResponse(
                success=False,
                message="Sync food items failed"
            ) 