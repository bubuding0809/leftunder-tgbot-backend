import asyncio
from json import load
import logging
import os
import telegram
import uuid
import base64
from telegram.ext import ContextTypes
from time import perf_counter
from datetime import datetime, timedelta
from typing import Literal, Optional, List
from pydantic import BaseModel, Field, ValidationError
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers.json import JsonOutputParser
from telegram import File, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from dotenv import load_dotenv

from api import Api
from schema import CreateFoodItemPayload, FoodItemBase
from utils import escape_markdown_v2

load_dotenv()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

FOOD_CATEGORY = Literal[
    "Fruits",
    "Vegetables",
    "Meat",
    "Dairy",
    "Snacks",
    "Beverages",
    "Grains",
    "Frozen Food",
    "Canned Food",
    "Pastries",
    "Cooked Food",
    "Others",
]

FOOD_UNIT = Literal[
    "g",
    "ml",
    "oz",
    "l",
    "kg",
    "piece",
    "packet",
    "bottle",
    "cup",
    "can",
    "box",
    "jar",
    "container",
    "carton",
    "serving",
    "others",
]


class FoodItem(BaseModel):
    food_name: str = Field(description="Name of the food item, keep it to max 3 words")
    category: FOOD_CATEGORY = Field(description="Type of the food item")
    description: str = Field(
        description="Description of the food item, keep it to 1 sentence long"
    )
    storage_instructions: str = Field(
        description="Storage instructions for the food item, be specific and detailed"
    )
    quantity: int = Field(
        description="Quantity of the food item, this should logically match the units. Try to keep it to the finest granularity possible."
    )
    units: FOOD_UNIT = Field(
        description="Units of the food item, this should logically match the quantity. Try to keep it to the finest granularity possible."
    )
    expiry_date: Optional[datetime] = Field(
        None, description="Expiry date of the food item"
    )
    shelf_life_days: Optional[int] = Field(
        None,
        description="Shelf life of the food item in days, estimate based on your knowledge or information available. If expiry date is provided, this field can be left empty. If expiry date is not provided, this field is required.",
    )
    percentage_remaining: int = Field(
        default=100,
        description="Percentage of volume or weight remaining in integer format, values between 0 and 100",
    )
    bounding_box: dict = Field(description="Bounding box coordinates of the food item in the image")


class LLMResponse(BaseModel):
    food_items: List[FoodItem] = Field(
        [], description="List of food items detected in the image"
    )


parser = PydanticOutputParser(
    pydantic_object=LLMResponse,
)

# Example usage
food_item_example = FoodItem(
    food_name="Oreo Pikachu Cookies",
    category="Snacks",
    description="These special edition Oreo cookies feature the iconic Pikachu from Pokémon, blended with the electrifying flavors of banana and chocolate cream.",
    storage_instructions="Store in a cool, dry place to keep the magic intact. Best enjoyed while binge-watching Pokémon episodes or trading cards.",
    quantity=1,
    units="packet",
    expiry_date=datetime(2024, 12, 21),
    shelf_life_days=365,
    percentage_remaining=100,
    bounding_box={"left": 100, "top": 50, "right": 300, "bottom": 250}
)

SYSTEM_PROMPT = """
You are a professional food cataloger. 
You assist the user by providing detailed and informative descriptions of images they upload.
Your main goal is to identify food items in the image and provide structured information about them.
You generate data in a structured format with specified fields for food items.

### Output Format Instructions:
{format_instructions}

Important: Ensure the data is structured in the format specified above.

### Example Output:
For food items detected: {positive_example}
For no food items detected: {negative_example}

Important: The example outputs above is provided for reference, ensure the data is structured in the format specified above.
"""


async def process_image(
    telegram_photo_file: File,
    telegram_chat_id: int,
    telegram_context: ContextTypes.DEFAULT_TYPE,
    photo_message_id: int,
    api: Api,
    loader_message_id: Optional[int] = None,
) -> None:
    # Download the photo as a byte array to process
    image_byte_array = await telegram_photo_file.download_as_bytearray()

    # Convert the image byte array to base64
    base64_image = base64.b64encode(image_byte_array).decode("utf-8")

    # Process the image using the LLM
    data = await invoke_chain(
        base64_image,
        telegram_chat_id=telegram_chat_id,
        loader_message_id=loader_message_id,
        photo_message_id=photo_message_id,
    )

    # Persist the generated data to the database

    # Parse the response data from the LLM and generate the message to send to the user
    if data is None:
        message_str = escape_markdown_v2(
            "🚨An error occurred while processing the image."
        )
    elif len(data.food_items) == 0:
        message_str = escape_markdown_v2("⚠️No food items detected in the image.")
    else:
        # Save the food items to the database
        food_item_payloads: List[FoodItemBase] = []
        for food_item in data.food_items:

            # If expiry date is not provided, calculate it based on shelf life days
            if food_item.expiry_date is None:
                food_item.expiry_date = datetime.now() + timedelta(
                    days=float(food_item.shelf_life_days or 0)
                )

            # Calculate the reminder date based on 2 days from the expiry date
            reminder_date = food_item.expiry_date - timedelta(days=2)

            food_item_payloads.append(
                FoodItemBase(
                    name=food_item.food_name,
                    description=food_item.description,
                    category=food_item.category,
                    storage_instructions=food_item.storage_instructions,
                    quantity=food_item.quantity,
                    unit=food_item.units,
                    expiry_date=food_item.expiry_date,
                    shelf_life_days=food_item.shelf_life_days,
                    reminder_date=reminder_date,
                )
            )

        await api.create_food_items(
            CreateFoodItemPayload(
                food_items=food_item_payloads,
                telegram_user_id=telegram_chat_id,
                image_base64=base64_image,
            )
        )

        # Format the json nicely to display in the message
        food_items = []
        for food_item in data.food_items:
            expiry_date = (
                datetime.strftime(food_item.expiry_date, "%Y-%m-%d")
                if food_item.expiry_date
                else str(None)
            )
            food_item_str = f"""
__*{escape_markdown_v2(food_item.food_name)}*__
Description: {escape_markdown_v2(food_item.description)}
Category: {escape_markdown_v2(food_item.category)}
Storage Instructions: {escape_markdown_v2(food_item.storage_instructions)}
Quantity/Units: {escape_markdown_v2(f"{food_item.quantity} {food_item.units}")}
Expiry Date: {escape_markdown_v2(expiry_date)}
Shelf Life \\(days\\): {escape_markdown_v2(str(food_item.shelf_life_days))}
Percentage Remaining: {escape_markdown_v2(str(food_item.percentage_remaining))}%
"""
            food_items.append(food_item_str)
        escaped_divider_str = escape_markdown_v2("\n---------\n")
        full_message_str = escaped_divider_str.join(food_items)
        short_message_str = "Found these food items:\n" + "\n".join(
            [
                f"{i}\\. __*{escape_markdown_v2(item.food_name)}*__"
                for i, item in enumerate(data.food_items, start=1)
            ]
        )
        message_str = full_message_str

        # Save the full message in the context data
        if telegram_context.user_data is not None:
            context_messages = telegram_context.user_data.get("messages", {})
            message = {
                "full": full_message_str,
                "short": short_message_str,
            }
            context_messages[photo_message_id] = message
            telegram_context.user_data["messages"] = context_messages

    # Send the result message to the user
    await send_telegram_result_message(
        telegram_chat_id=telegram_chat_id,
        loader_message_id=loader_message_id,
        photo_message_id=photo_message_id,
        message_str=message_str,
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    "edit",
                    web_app=WebAppInfo(url="https://github.com/bubuding0809"),
                ),
            ],
        ],
    )


async def invoke_chain(
    base64_image: str,
    telegram_chat_id: int,
    photo_message_id: Optional[int],
    loader_message_id: Optional[int] = None,
) -> Optional[LLMResponse]:
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0.5,
    )

    # Construct system message content
    positive_example = LLMResponse(food_items=[food_item_example])
    negative_example = LLMResponse(food_items=[])
    system_message_content = SYSTEM_PROMPT.format(
        format_instructions=parser.get_format_instructions(),
        positive_example=positive_example,
        negative_example=negative_example,
    )

    # Construct prompt
    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessage(content=system_message_content),
            HumanMessage(
                content=[
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": "high",
                        },
                    }
                ]
            ),
        ],
    )

    chain = prompt | llm | JsonOutputParser(pydantic_object=LLMResponse)
    chain = chain.with_retry()

    # Invoke the chain with the prepared prompt
    logging.info(f"Invoking chain for {photo_message_id}")
    start_time = perf_counter()
    try:
        response = await chain.ainvoke({})
    except Exception as e:
        logging.error(f"Error invoking chain for {photo_message_id}: {e}")
        return None
    logging.info(
        f"Received response for {photo_message_id}, took {perf_counter() - start_time:.2f}s"
    )

    try:
        return LLMResponse(**response)
    except ValidationError as e:
        logging.error(f"Error parsing response for {photo_message_id}: {e}")
        return None


async def send_telegram_result_message(
    telegram_chat_id: int,
    message_str: str,
    loader_message_id: Optional[int] = None,
    photo_message_id: Optional[int] = None,
    **kwargs,
) -> None:
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

    inline_keyboard = kwargs.get("inline_keyboard", None)

    try:
        # Reply to image with result message
        await bot.send_message(
            chat_id=telegram_chat_id,
            text=message_str,
            parse_mode="MarkdownV2",
            reply_markup=(
                InlineKeyboardMarkup(inline_keyboard) if inline_keyboard else None
            ),
            reply_to_message_id=photo_message_id,
        )

        # Delete original loader message
        if loader_message_id:
            await bot.delete_message(
                chat_id=telegram_chat_id, message_id=loader_message_id
            )
        logging.info(f"Sent message to Telegram: {photo_message_id}: {message_str}")
    except telegram.error.TelegramError as e:
        logging.error(
            f"Error sending message to Telegram: {photo_message_id}: {e.message}"
        )
    except Exception as e:
        logging.error(f"Error sending message to Telegram: {photo_message_id}: {e}")


def main():
    pass


if __name__ == "__main__":
    main()
