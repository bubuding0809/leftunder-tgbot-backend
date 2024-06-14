from api import Api
from fastapi import FastAPI, HTTPException, Body
from typing import List
from pydantic import BaseModel
from uuid import UUID, uuid4
from supabase import create_client, Client

from schema import *

app = FastAPI()

supabase_url: str = "your_supabase_url" # TODO
supabase_key: str = "your_supabase_key" # TODO

api_instance = Api(supabase_url, supabase_key)

@app.get("/")
def read_root():
    return {"Hello": "World"}

# Food Item Endpoints

@app.post("/create-food-items-for-user/", response_model=CreateFoodItemResponse)
def create_food_items_for_user(payload: CreateFoodItemPayload = Body(...)):
    return api_instance.create_food_items(payload)
    

@app.get("/read-food-items-for-user/", response_model=ReadFoodItemResponse)
def read_food_items_for_user(telegram_user_id: int):
    return api_instance.read_food_items_for_user(telegram_user_id=telegram_user_id)

@app.put("/update-food-items-for-user/", response_model=UpdateFoodItemResponse)
def update_food_items_for_user(payload: UpdateFoodItemPayload = Body(...)):
    return api_instance.update_food_items(payload)

@app.put("/sync-reminder-food-items-for-user/", response_model=CreateFoodItemResponse)
def update_food_items_for_user():
    return api_instance.sync_reminder_date_food_items()

@app.delete("/food-items/{food_item_id}", response_model=FoodItem)
def delete_food_item(food_item_id: UUID):
    if food_item_id not in fake_food_db:
        raise HTTPException(status_code=404, detail="Food item not found")
    return fake_food_db.pop(food_item_id)


# User Endpoints
@app.get("/users/telegram_user_id/{telegram_user_id}", response_model=GetUserResponse)
def read_user(telegram_user_id: int):
    return api_instance.get_user(GetUserPayload(telegram_user_id=telegram_user_id))
