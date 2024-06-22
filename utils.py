import base64
from datetime import datetime, timedelta, timezone
from PIL import Image
from io import BytesIO
import uuid
import os
import requests

from schema import ConsumedDiscardedFoodItemPayload, FoodItemConsumedDiscarded

def escape_markdown_v2(text: str) -> str:
    """
    Escapes special characters in the given text to prevent them from being interpreted as Markdown formatting.

    Args:
      text (str): The input text to escape.

    Returns:
      str: The escaped text.
    """

    special_chars = [
        "_",
        "*",
        "[",
        "]",
        "(",
        ")",
        "~",
        "`",
        ">",
        "#",
        "+",
        "-",
        "=",
        "|",
        "{",
        "}",
        ".",
        "!",
    ]
    escaped_text = ""
    for char in text:
        if char in special_chars:
            escaped_text += "\\" + char
        else:
            escaped_text += char
    return escaped_text

def crop_and_return_base64_image(image_base64: str, bounding_box: dict) -> str:
    # Decode base64 image data to binary
    image_data = base64.b64decode(image_base64)
    
    # Open the image using PIL (Python Imaging Library)
    image = Image.open(BytesIO(image_data))
    
    # Extract bounding box coordinates
    left = bounding_box['left']
    top = bounding_box['top']
    right = bounding_box['right']
    bottom = bounding_box['bottom']
    
    # Crop the image using bounding box coordinates
    cropped_image = image.crop((left, top, right, bottom))
    
    # Convert cropped image to base64-encoded string
    buffered = BytesIO()
    cropped_image.save(buffered, format="JPEG")
    cropped_image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    return cropped_image_base64

def calculate_reminder_date(food_item):
    # If expiry date is not provided, calculate it based on shelf life days
    if food_item.expiry_date is None:
        food_item.expiry_date = datetime.now() + timedelta(
            days=float(food_item.shelf_life_days or 0)
        )

    # Calculate the reminder date based on 5 days from the expiry date
    reminder_date = food_item.expiry_date - timedelta(days=5)

    return reminder_date

def send_telegram_message(bot_token, chat_id, message, buttons=None):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    reply_markup = {}
    
    if buttons:
        # Prepare inline keyboard markup
        keyboard = []
        for row in buttons:
            keyboard.append([{"text": btn_text, "url": btn_url} for btn_text, btn_url in row])
        reply_markup = {"inline_keyboard": keyboard}

    payload = {
        "chat_id": chat_id,
        "text": message,
        "reply_markup": reply_markup,
        "parse_mode": "markdown"  # Set parse mode to Markdown V2
    }
    
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print("Message sent successfully")
    else:
        print(f"Failed to send message. Status code: {response.status_code}")

  
def format_expiry_alert(food_items):
    messages = []
    today_iso: datetime = datetime.now(tz=timezone.utc)

    for food_item in food_items:
        name = food_item.name
        expiry_date: datetime = food_item.expiry_date

        if expiry_date is None:
            expiry_status = "Unknown"
        else:
            # Calculate the difference in days
            days_until_expiry = (expiry_date - today_iso).days - 1
            
            if days_until_expiry == 0:
                expiry_status = f"expiring today: *{expiry_date.strftime('%Y-%m-%d')}*"
            elif days_until_expiry < 0:
                expiry_status = f"expired on: *{expiry_date.strftime('%Y-%m-%d')}*"
            else:
                expiry_status = f"expiring in {days_until_expiry} day(s): *{expiry_date.strftime('%Y-%m-%d')}*"

        message = f"- {name} ({expiry_status})"
        messages.append(message)
    
    alert_message = (
        "*Food Expiry Alert* 🍟🍣🌽🍒🥬🍢\n\n" 
        + "⏰ These food items are expiring soon!!!\n\n"
        + "\n".join(messages)
        + "\n\n\n📱Manage your *pantry* in the miniapp!\n⬇️⬇️⬇️"
    )

    return alert_message