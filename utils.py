import base64
from datetime import datetime, timedelta
from PIL import Image
from io import BytesIO
import uuid

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

    # Calculate the reminder date based on 2 days from the expiry date
    reminder_date = food_item.expiry_date - timedelta(days=2)

    return reminder_date