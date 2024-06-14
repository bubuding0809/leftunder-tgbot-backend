from fastapi import FastAPI, HTTPException
from typing import List
from pydantic import BaseModel
from uuid import UUID, uuid4

app = FastAPI()

class FoodItem(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    price: float
    tax: Optional[float] = None

class User(BaseModel):
    id: UUID
    username: str
    email: str
    full_name: Optional[str] = None
    disabled: Optional[bool] = None

fake_food_db = {}
fake_user_db = {}

@app.get("/")
def read_root():
    return {"Hello": "World"}

# Food Item Endpoints

@app.get("/food-items/", response_model=List[FoodItem])
def read_food_items(skip: int = 0, limit: int = 10):
    items = list(fake_food_db.values())[skip : skip + limit]
    return items

@app.get("/food-items/{food_item_id}", response_model=FoodItem)
def read_food_item(food_item_id: UUID):
    if food_item_id not in fake_food_db:
        raise HTTPException(status_code=404, detail="Food item not found")
    return fake_food_db[food_item_id]

@app.put("/food-items/{food_item_id}", response_model=FoodItem)
def update_food_item(food_item_id: UUID, food_item: FoodItem):
    if food_item_id not in fake_food_db:
        raise HTTPException(status_code=404, detail="Food item not found")
    fake_food_db[food_item_id] = food_item
    return food_item

@app.delete("/food-items/{food_item_id}", response_model=FoodItem)
def delete_food_item(food_item_id: UUID):
    if food_item_id not in fake_food_db:
        raise HTTPException(status_code=404, detail="Food item not found")
    return fake_food_db.pop(food_item_id)

# User Endpoints

@app.get("/users/{user_id}", response_model=User)
def read_user(user_id: UUID):
    if user_id not in fake_user_db:
        raise HTTPException(status_code=404, detail="User not found")
    return fake_user_db[user_id]

@app.put("/users/{user_id}", response_model=User)
def update_user(user_id: UUID, user: User):
    if user_id not in fake_user_db:
        raise HTTPException(status_code=404, detail="User not found")
    fake_user_db[user_id] = user
    return user
