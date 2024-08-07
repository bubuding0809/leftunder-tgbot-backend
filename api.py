from collections import defaultdict
from datetime import datetime, timedelta, timezone
import logging
import os
from time import perf_counter
import telegram
import llm
from dotenv import load_dotenv
from pydantic import ValidationError
from supabase import acreate_client
from typing import Dict, List
from utils import (
    calculate_reminder_date,
    escape_markdown_v2,
    format_expiry_alert,
    send_telegram_message,
)
from schema import (
    BaseResponse,
    CreateFoodItemPayload,
    FoodItemBase,
    UpdateFoodItemPayload,
    CreateFoodItemResponse,
    ReadFoodItemResponse,
    UpdateFoodItemResponse,
    FoodItemResponse,
    GetUserPayload,
    GetUserResponse,
    RegisterUserPayload,
    RegisterUserResponse,
    User,
    FoodItemUpdate,
)

load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
logger = logging.getLogger(__name__)


class Api:
    def __init__(self):
        self._supabase = None
        self.telegram_bot = telegram.Bot(
            token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            request=telegram.request.HTTPXRequest(),
        )
        logger.info("API initialized")

    async def get_supabase_client(self):
        if self._supabase is None:
            self._supabase = await acreate_client(SUPABASE_URL, SUPABASE_KEY)
        return self._supabase

    async def process_image(
        self,
        image_url: str,
        telegram_user_id: int,
    ) -> str:
        # Process the image using the LLM
        start_time = perf_counter()
        logger.info(f"Invoking llm to process: {image_url.split('/')[-1]}")
        llm_response = await llm.invoke_chain(image_url)
        logger.info(
            f"Completed processing for {image_url.split('/')[-1]} in {perf_counter() - start_time:.2f}s - {[food_item.food_name for food_item in llm_response.food_items] if llm_response else []}"
        )

        if llm_response is None:
            return escape_markdown_v2(
                "🚨 An error occurred while processing the image, please try again."
            )

        if len(llm_response.food_items) == 0:
            return escape_markdown_v2("⚠️ No food items detected in the image.")

        food_item_payloads: List[FoodItemBase] = []
        food_item_strs: List[str] = []
        for food_item in llm_response.food_items:
            # If expiry date is not provided, calculate it based on shelf life days
            if food_item.expiry_date is None:
                food_item.expiry_date = datetime.now() + timedelta(
                    days=float(food_item.shelf_life_days or 0)
                )

            # Calculate the reminder date based on 2 days from the expiry date
            REMINDER_DELTA = 5
            reminder_date = food_item.expiry_date - timedelta(days=REMINDER_DELTA)

            food_item_payloads.append(
                FoodItemBase(
                    name=food_item.food_name,
                    description=food_item.description,
                    category=food_item.category,
                    storage_instructions=food_item.storage_instructions,
                    quantity=food_item.quantity,
                    unit=food_item.unit,
                    expiry_date=food_item.expiry_date,
                    reminder_date=reminder_date,
                )
            )

            # Construct the message for each food item
            food_item_strs.append(
                f""">__*{escape_markdown_v2(food_item.food_name)} \\({escape_markdown_v2(f"{food_item.quantity} {food_item.unit}")}\\)*__
>📖 \\- {escape_markdown_v2(food_item.description)}
>🗄 \\- {escape_markdown_v2(food_item.storage_instructions)}
>⏳ \\- Use by {escape_markdown_v2(datetime.strftime(food_item.expiry_date, "%Y-%m-%d"))}"""
            )

        # Persist the generated data to the database
        create_food_items_response = await self._create_food_items(
            CreateFoodItemPayload(
                food_items=food_item_payloads,
                telegram_user_id=telegram_user_id,
                image_url=image_url,
            )
        )

        # Return an error message if the food items were not created successfully
        if not create_food_items_response.success:
            return escape_markdown_v2(
                f"😥 Sorry, something went wrong while saving these food items to the pantry"
            )

        # Return the results message
        escaped_divider_str = "\n>\n"
        message = escaped_divider_str.join(food_item_strs)
        message = "**>" + message + "||"
        return (
            f"*✨🔮Found {len(food_item_strs)} food item{'s' if len(food_item_strs) > 1 else ''}🔮✨*\n\n"
            + message
            + "\n\n\n📱Manage your *pantry* in the miniapp\\!\n⬇️⬇️⬇️"
        )

    async def get_user(self, payload: GetUserPayload) -> GetUserResponse:
        supabase_client = await self.get_supabase_client()

        try:
            response = await (
                supabase_client.table("User")
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

    async def register_user(self, payload: RegisterUserPayload) -> RegisterUserResponse:
        supabase_client = await self.get_supabase_client()
        try:
            response = (
                await supabase_client.table("User")
                .insert(payload.model_dump())
                .execute()
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

    async def _create_food_items(
        self, payload: CreateFoodItemPayload
    ) -> CreateFoodItemResponse:
        supabase_client = await self.get_supabase_client()

        user_response = await self.get_user(
            GetUserPayload(telegram_user_id=payload.telegram_user_id)
        )
        user = user_response.user
        if user is None:
            return CreateFoodItemResponse(success=False, message="User not found")

        food_item_payloads: List[Dict] = []
        for item in payload.food_items:
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
                "image_url": payload.image_url,
                "consumed": False,
                "discarded": False,
            }
            food_item_payloads.append(food_item_payload_data)

        # Insert the food items into the Supabase database
        try:
            response = await (
                supabase_client.table("FoodItem").insert(food_item_payloads).execute()
            )
        except Exception as e:
            logger.info("Error creating food items", e)
            return CreateFoodItemResponse(success=False, message=str(e))

        # Parse the response data into FoodItemResponse objects
        try:
            food_items = [FoodItemResponse(**item) for item in response.data]
            return CreateFoodItemResponse(
                success=True, message="Food item created", food_items=food_items
            )
        except ValidationError as e:
            logger.info("Error parsing food items", e)
            return CreateFoodItemResponse(success=False, message=str(e))

    async def read_food_items_for_user(
        self, telegram_user_id: int
    ) -> ReadFoodItemResponse:
        supabase_client = await self.get_supabase_client()

        user_response: GetUserResponse = await self.get_user(
            GetUserPayload(telegram_user_id=telegram_user_id)
        )
        user = user_response.user
        if user is None:
            return ReadFoodItemResponse(success=False, message="User not found")

        try:
            response = await (
                supabase_client.table("FoodItem")
                .select("*")
                .eq("user_id", user.id)
                .order("created_at")
                .execute()
            )
            food_items = [FoodItemResponse(**item) for item in response.data]
            return ReadFoodItemResponse(
                success=True,
                message="Food items read successfully",
                food_items=food_items,
            )
        except Exception as e:
            logger.info("Error reading food items", e)
            return ReadFoodItemResponse(success=False, message=str(e))

    async def update_food_items(
        self, payload: UpdateFoodItemPayload
    ) -> UpdateFoodItemResponse:
        supabase_client = await self.get_supabase_client()

        user_response = await self.get_user(
            GetUserPayload(telegram_user_id=payload.telegram_user_id)
        )
        user = user_response.user
        if user is None:
            return UpdateFoodItemResponse(success=False, message="User not found")

        food_items_updated_success: List[FoodItemResponse] = []
        food_items_updated_failed: List[FoodItemUpdate] = []

        food_item_payloads: List[FoodItemUpdate] = []
        for update_item in payload.food_items:
            food_item_id = update_item.id

            updated_data = {
                "name": update_item.name,
                "description": update_item.description,
                "category": update_item.category,
                "storage_instructions": update_item.storage_instructions,
                "quantity": update_item.quantity,
                "unit": update_item.unit,
                "expiry_date": (
                    update_item.expiry_date.isoformat()
                    if update_item.expiry_date
                    else None
                ),
                "shelf_life_days": update_item.shelf_life_days,
                "reminder_date": calculate_reminder_date(update_item).isoformat(),
                "consumed": update_item.consumed,
                "discarded": update_item.discarded,
            }

            try:
                response = await (
                    supabase_client.table("FoodItem")
                    .update(updated_data)
                    .eq("id", food_item_id)
                    .execute()
                )
                food_items = [FoodItemResponse(**item) for item in response.data]
                food_items_updated_success.extend(food_items)
            except Exception as e:
                logger.info(f"Error updating food items of id {food_item_id}", e)
                food_items_updated_failed.append(update_item)
                continue

        return UpdateFoodItemResponse(
            success=True,
            message="Food items updated",
            food_items_updated_success=food_items_updated_success,
            food_items_updated_failed=food_items_updated_failed,
        )

    async def sync_reminder_date_food_items(
        self, days_to_expiry: int, telegram_user_id: int
    ) -> BaseResponse:
        TEST_USER_TO_SEND_TELEGRAM_TO: int = telegram_user_id

        # Get current datetime
        current_datetime = datetime.now(tz=timezone.utc)
        current_datetime_iso = current_datetime.isoformat()
        # new reminder datetime is 23 hours from current datetime
        next_reminder_datetime = current_datetime + timedelta(hours=23)
        next_reminder_datetime_iso = next_reminder_datetime.isoformat()

        trigger_date = current_datetime + timedelta(days=days_to_expiry)
        trigger_date_iso = trigger_date.isoformat()

        supabase_client = await self.get_supabase_client()

        TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

        try:
            response_read = (
                await supabase_client.table("FoodItem")
                .select("*")
                .eq("consumed", False)
                .eq("discarded", False)
                .lt("expiry_date", trigger_date_iso)
                .order("expiry_date")
                .execute()
            )

            # response = await supabase_client.table("FoodItem").update({"reminder_date": next_reminder_datetime_iso}).eq("consumed", False).eq("discarded", False).lt("expiry_date", trigger_date_iso).execute()
            food_items_remove_none_reminder_date = [
                item
                for item in response_read.data
                if item.get("reminder_date") is not None
                or datetime.fromisoformat(item["expiry_date"])
                > datetime.fromisoformat(current_datetime_iso)
            ]
            food_items = [
                FoodItemResponse(**item)
                for item in food_items_remove_none_reminder_date
            ]

            expired_items = []
            for item in food_items_remove_none_reminder_date:
                if datetime.fromisoformat(item["expiry_date"]) < datetime.fromisoformat(
                    current_datetime_iso
                ):
                    expired_items.append(
                        item["id"]
                    )  # Assuming 'id' is the primary key or identifier for the FoodItem table
                    item["reminder_date"] = None

            # Update expired items in the database
            if expired_items:
                await supabase_client.table("FoodItem").update(
                    {"reminder_date": None}
                ).in_("id", expired_items).execute()

        except Exception as e:
            return BaseResponse(
                success=False,
                message="Failed to fetch expiring items - Sync food items failed",
            )

        grouped_food_items = defaultdict(list)
        for food_item_response_obj in food_items:
            grouped_food_items[food_item_response_obj.user_id].append(
                food_item_response_obj
            )
        # Convert the defaultdict to a regular dictionary
        grouped_food_items = dict(grouped_food_items)

        try:
            for id_user_table, user_food_items_list in grouped_food_items.items():
                telegram_user_id_resp = (
                    await supabase_client.table("User")
                    .select("telegram_user_id")
                    .eq("id", id_user_table)
                    .execute()
                )

                telegram_user_id = telegram_user_id_resp.data[0]["telegram_user_id"]
                telegram_user_alert_message = format_expiry_alert(user_food_items_list)
                if (
                    TEST_USER_TO_SEND_TELEGRAM_TO == 0
                    or telegram_user_id == TEST_USER_TO_SEND_TELEGRAM_TO
                ):
                    send_telegram_message(
                        TELEGRAM_BOT_TOKEN,
                        telegram_user_id,
                        telegram_user_alert_message,
                    )

            return BaseResponse(
                success=True,
                message="Sync food items success - message sent to telegram user",
            )
        except Exception as e:
            return BaseResponse(
                success=False,
                message="Unable to send telegram message - Sync food items failed",
            )
