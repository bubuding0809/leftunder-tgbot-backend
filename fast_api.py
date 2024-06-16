from api import Api
from fastapi import FastAPI, HTTPException, Body, Query
from typing import List
from pydantic import BaseModel
from uuid import UUID, uuid4
from supabase import create_client, Client
import os

from schema import *

app = FastAPI()

supabase_url: str = os.environ.get("SUPABASE_URL", "")
supabase_key: str = os.environ.get("SUPABASE_KEY", "")

api_instance = Api(supabase_url, supabase_key)

@app.get("/")
def read_root():
    return {"Hello": "World"}

# Food Item Endpoints

@app.post("/create-food-items-for-user/", response_model=CreateFoodItemResponse)
async def create_food_items_for_user(payload: CreateFoodItemPayload = Body(...)):
    return await api_instance.create_food_items(payload)

@app.get("/read-food-items-for-user/", response_model=ReadFoodItemResponse)
async def read_food_items_for_user(
    telegram_user_id: int = Query(..., description="Telegram user ID"),
    order_by: str = Query("expiry_date", description="Ordering criteria (expiry_date, created_at)"),
    sort: str = Query("desc", description="Sorting criteria (asc, desc)")
    ):
    return await api_instance.read_food_items_for_user(telegram_user_id=telegram_user_id, order_by=order_by, sort=sort)

@app.put("/update-food-items-for-user/", response_model=UpdateFoodItemResponse)
async def update_food_items_for_user(payload: UpdateFoodItemPayload = Body(...)):
    return await api_instance.update_food_items(payload)

@app.get("/trigger-reminder-food-items-for-user/", response_model=BaseResponse)
def sync_food_items_for_user(days_to_expiry: int = Query(5, description="days within expiry to trigger notification")):
    return api_instance.sync_reminder_date_food_items()

# @app.post("/delete-food-items/", response_model=DeleteFoodItemResponse)
# def delete_food_item(payload: DeleteFoodItemPayload):
#     return api_instance.delete_food_items_for_user(payload)

# User Endpoints
# @app.get("/users/telegram_user_id/{telegram_user_id}", response_model=GetUserResponse)
# def read_user(telegram_user_id: int):
#     return api_instance.get_user(GetUserPayload(telegram_user_id=telegram_user_id))
