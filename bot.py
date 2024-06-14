import asyncio
import logging
import os
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    WebAppInfo,
)
import telegram
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from dotenv import load_dotenv
from api import Api
import llm
from schema import GetUserPayload, RegisterUserPayload

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

START_MESSAGE_EXISITING = """
Welcome back to Leftunder, {username}! 🌟 We're thrilled to see you again. Here's a quick reminder of the great features you can start using right away.

📋 Pantry Tracker: Organize pantry items and track expiration dates. 

💡 Storage Tips: Maximize shelf life with expert storage advice.

🍲 Recipe Generator 🚧: Get recipes based on your available ingredients.

💚 Support Your Community 🚧: Share surplus or find essentials with a tap, ensuring nothing goes to waste.

Start by sending a picture or multiple pictures 📸 of the food items you want to track!
"""

START_MESSAGE_NEW = """
Welcome to LeftUnder, {user}! 🎉

We have just signed you up for the LeftUnder food tracker.

Try the food tracker by sending a picture or multiple pictures 📸 of the food items you want to track! 🥗🍎🥖
"""

HELP_MESSAGE = """
Forgot how to use the bot? 🤣

Here’s a quick guide to get you started:

1.	📸 Send pictures of the food item you want to the bot.
2.	⏳ Wait for the bot to identify the food item.
3.	🗂️ Manage your food items in the pantry tracker by clicking on the mini-app menu button next to the chat box.
4.	⏰ Get automatic reminders when your food items are about to expire.
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, api: Api):
    if update.effective_chat is None:
        return

    # Check if the user is already registered
    response = api.get_user(GetUserPayload(telegram_user_id=update.effective_chat.id))
    message = START_MESSAGE_EXISITING.format(username=update.effective_chat.first_name)

    # Register the user if not already registered
    if response.user is None:
        api.register_user(
            RegisterUserPayload(
                telegram_user_id=update.effective_chat.id,
                telegram_username=update.effective_chat.username or "",
                first_name=update.effective_chat.first_name or "",
                last_name=update.effective_chat.last_name or "",
            )
        )
        message = START_MESSAGE_NEW.format(user=update.effective_chat.first_name)

    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat is None:
        return

    await context.bot.send_message(chat_id=update.effective_chat.id, text=HELP_MESSAGE)


async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat is None:
        return

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Oops...😱 I can't converse but do send me 📸 some food pictures so I can tracking!",
    )


async def photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE, api: Api):
    if update.effective_chat is None:
        return

    # Process the photo(s) sent by the user
    if update.effective_message is None:
        return

    # Download the photo and send it to the LLM for
    target_photo = update.effective_message.photo[-1]

    # Reply to image message with a loading sticker
    try:
        with open("assets/searching.tgs", "rb") as sticker_file:
            loader_message = await context.bot.send_sticker(
                chat_id=update.effective_chat.id,
                sticker=sticker_file,
                reply_to_message_id=update.effective_message.message_id,
            )
    except telegram.error.TelegramError as e:
        logging.error(f"Error sending sticker: {e.message}")
    except FileNotFoundError as e:
        logging.error(f"Error sending sticker: {e}")
    except Exception as e:
        logging.error(f"Error sending sticker: {e}")

    # Process the image using LLM as a asynchronous task
    photo_file = await target_photo.get_file()
    asyncio.create_task(
        llm.process_image(
            photo_file,
            telegram_chat_id=update.effective_chat.id,
            loader_message_id=loader_message.message_id if loader_message else None,
            photo_message_id=update.effective_message.message_id,
            telegram_context=context,
            api=api,
        )
    )


async def show_more(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is None:
        return
    await update.callback_query.answer()

    # Retrieve the callback data
    callback_data = update.callback_query.data
    if callback_data is None:
        return

    target_message_id = callback_data.split(":")[-1]
    if target_message_id is None:
        return

    # Retrieve context data
    if context.user_data is None:
        return
    messages = context.user_data.get("messages")
    if messages is None:
        return
    show_more_message = messages[int(target_message_id)]["full"]

    if update.effective_chat is None:
        return

    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=int(target_message_id),
        text=show_more_message,
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "↑ Show less", callback_data=f"show_less:{target_message_id}"
                    ),
                    InlineKeyboardButton(
                        "edit",
                        web_app=WebAppInfo(url="https://github.com/bubuding0809"),
                    ),
                ],
            ]
        ),
    )


async def show_less(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is None:
        return
    await update.callback_query.answer()

    # Retrieve the callback data
    callback_data = update.callback_query.data
    if callback_data is None:
        return

    target_message_id = callback_data.split(":")[-1]
    if target_message_id is None:
        return

    # Retrieve context data
    if context.user_data is None:
        return
    messages = context.user_data.get("messages")
    if messages is None:
        return
    show_less_message = messages[int(target_message_id)]["short"]

    if update.effective_chat is None:
        return

    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=int(target_message_id),
        text=show_less_message,
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "↓ Show more", callback_data=f"show_more:{target_message_id}"
                    ),
                    InlineKeyboardButton(
                        "edit",
                        web_app=WebAppInfo(url="https://github.com/bubuding0809"),
                    ),
                ],
            ]
        ),
    )


async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Update {update} caused error {context.error}")


def main(api: Api):
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Define handlers
    start_handler = CommandHandler(
        "start",
        lambda update, context: start(update, context, api),
    )
    show_more_handler = CallbackQueryHandler(show_more, pattern="^show_more:.*")
    show_less_handler = CallbackQueryHandler(show_less, pattern="^show_less:.*")
    photo_message_handler = MessageHandler(
        filters.PHOTO,
        lambda update, context: photo_message(update, context, api),
    )
    help_handler = CommandHandler("help", help)
    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, message)

    # Register handlers
    application.add_handler(start_handler)
    application.add_handler(help_handler)
    application.add_handler(message_handler)
    application.add_handler(photo_message_handler)
    application.add_handler(show_more_handler)
    application.add_handler(show_less_handler)
    application.add_error_handler(error)  # type: ignore

    # Run the bot in polling mode or webhook mode depending on the environment
    PRODUCTION = os.environ.get("PRODUCTION", False) == "True"
    if PRODUCTION:
        application.run_webhook()
    else:
        application.run_polling()


if __name__ == "__main__":
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")
    main(Api(supabase_url, supabase_key))
