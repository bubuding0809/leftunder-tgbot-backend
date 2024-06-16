import logging
import os
from datetime import datetime
from typing import Literal, Optional, List
from pydantic import BaseModel, Field, ValidationError
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers.json import JsonOutputParser
from dotenv import load_dotenv

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

FOOD_UNIT = [
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
    "bowl",
    "carton",
    "serving",
    "others",
]


class FoodItem(BaseModel):
    """Food item detected in the image"""

    food_name: str = Field(description="Name of the food item, keep it to max 3 words")
    category: FOOD_CATEGORY = Field(description="Type of the food item")
    description: str = Field(
        description="Description of the food item, keep it to 1 sentence long"
    )
    storage_instructions: str = Field(
        description="Storage instructions for the food item, be specific and detailed"
    )
    quantity: float = Field(
        description="Quantity of the food item, this should logically match the unit. Try to keep it to the finest granularity possible."
    )
    unit: str = Field(
        description=f"Unit of the food item, this should logically match the quantity. Try to keep it to the finest granularity possible. Only use the unit provided in the list {FOOD_UNIT}"
    )
    expiry_date: Optional[datetime] = Field(
        None, description="Expiry date of the food item"
    )
    shelf_life_days: Optional[int] = Field(
        None,
        description="Shelf life of the food item in days, estimate based on your knowledge or information available. If expiry date is provided, this field can be left empty. If expiry date is not provided, this field is required.",
    )


class LLMResponse(BaseModel):
    """Food items detected in the image"""

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
    unit="packet",
    expiry_date=datetime(2024, 12, 21),
    shelf_life_days=365,
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


async def invoke_chain(
    image_url: str,
) -> Optional[LLMResponse]:
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0.6,
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
                        "image_url": {"url": image_url, "detail": "high"},
                    }
                ]
            ),
        ],
    )

    chain = prompt | llm | JsonOutputParser(pydantic_object=LLMResponse)
    chain = chain.with_retry()

    # Invoke the chain with the prepared prompt
    try:
        response = await chain.ainvoke({})
    except Exception as e:
        logging.error(f"Error invoking chain: {e}")
        return None

    try:
        return LLMResponse(**response)
    except ValidationError as e:
        logging.error(f"Error parsing response for: {e}")
        return None


def main():
    pass


if __name__ == "__main__":
    main()
    