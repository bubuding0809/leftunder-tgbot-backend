import html
import json
import logging
import os
import traceback
from typing import Optional
import uuid
import telegram
from telegram import (
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)
from dotenv import load_dotenv
from api import Api
from schema import GetUserPayload, RegisterUserPayload

load_dotenv()
SUPABASE_STORAGE_PUBLIC_URL = os.environ.get("SUPABASE_STORAGE_PUBLIC_URL")
TELEGRAM_LOG_CHANNEL_ID = os.environ.get("TELEGRAM_LOG_CHANNEL_ID", "")

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

# Initialize the API client
api = Api()


# * Start handler - process the start command sent by the user to register the user or welcome back
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat is None:
        return

    # Check if the user is already registered
    response = await api.get_user(
        GetUserPayload(telegram_user_id=update.effective_chat.id)
    )
    message = START_MESSAGE_EXISITING.format(username=update.effective_chat.first_name)

    # Register the user if not already registered
    if response.user is None:
        await api.register_user(
            RegisterUserPayload(
                telegram_user_id=update.effective_chat.id,
                telegram_username=update.effective_chat.username or "",
                first_name=update.effective_chat.first_name or "",
                last_name=update.effective_chat.last_name or "",
            )
        )
        message = START_MESSAGE_NEW.format(user=update.effective_chat.first_name)

    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)


# * Help handler - process the help command sent by the user to inform about the bot's capabilities
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat is None:
        return

    await context.bot.send_message(chat_id=update.effective_chat.id, text=HELP_MESSAGE)


# * Message handler - process the message sent by the user to inform that the bot can't converse
async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat is None:
        return

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Oops...😱 I can't converse but do send me 📸 some food pictures so I can tracking!",
    )


# * Photo handler - process the photo sent by the user to extract food information
async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat is None:
        return

    # Process the photo(s) sent by the user
    if update.effective_message is None:
        return

    # Download the photo and send it to the LLM for
    target_photo = update.effective_message.photo[-1]

    # Reply to image message with a loading message to indicate processing of the image
    loader_message = await context.bot.send_message(
        text="🔍Extracting food information✨\n⏱️_Ready in 10 \\- 15s🙏_",
        chat_id=update.effective_chat.id,
        reply_to_message_id=update.effective_message.message_id,
        parse_mode=ParseMode.MARKDOWN_V2,
        read_timeout=60,
        write_timeout=60,
        connect_timeout=60,
    )

    # Download the photo and send it to the LLM for processing
    photo_file = await target_photo.get_file()
    image_bytearray = await photo_file.download_as_bytearray()

    # Upload the image to Supabase storage to get a public URL for passing to the LLM
    supabase_client = await api.get_supabase_client()
    bucket = supabase_client.storage.from_("public-assets")
    try:
        image_path = f"{uuid.uuid4()}.jpg"
        image_response = await bucket.upload(
            path=image_path,
            file=bytes(image_bytearray),
            file_options={"content-type": "image/jpeg"},
        )
        image_key: str = image_response.json()["Key"]
        image_url = f"{SUPABASE_STORAGE_PUBLIC_URL}/{image_key}"
    except Exception as e:
        image_url = None
        logging.error(f"Error uploading image: {e}")

    # If the image is not uploaded successfully, send an error message
    if image_url is None:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⛔️ Error processing image. Please try again.",
            reply_to_message_id=update.effective_message.message_id,
            read_timeout=60,
            write_timeout=60,
            connect_timeout=60,
        )
        return

    # TODO - replace with API call to separate service
    try:
        results_message = await api.process_image(
            image_url=image_url,
            telegram_user_id=update.effective_chat.id,
        )
    except Exception as e:
        results_message = "⛔️ Error processing image. Please try again."
        logging.error(f"Error processing image: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=results_message,
            reply_to_message_id=update.effective_message.message_id,
            read_timeout=60,
            write_timeout=60,
            connect_timeout=60,
        )

    # Remove the loader message to indicate completion of processing
    await context.bot.delete_message(
        chat_id=update.effective_chat.id,
        message_id=loader_message.message_id,
        read_timeout=60,
        write_timeout=60,
        connect_timeout=60,
    )

    # Send a results message to indicate the food items detected
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=results_message,
        reply_to_message_id=update.effective_message.message_id,
        parse_mode="MarkdownV2",
        read_timeout=60,
        write_timeout=60,
        connect_timeout=60,
    )


# * Error handler - process the error caused by the update
async def error(update: Optional[object], context: ContextTypes.DEFAULT_TYPE):
    """Log the error and send a formatted message to the user/developer."""

    if context.error is None:
        return

    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error("Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(
        None, context.error, context.error.__traceback__
    )
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        "An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    # Finally, let's send this message to the developer so they know something went wrong.
    if (
        update is not None
        and isinstance(update, Update)
        and update.effective_message is not None
    ):
        try:
            await context.bot.send_message(
                chat_id=TELEGRAM_LOG_CHANNEL_ID,
                text=message,
                parse_mode=ParseMode.HTML,
            )
        except telegram.error.TelegramError as e:
            logger.error(f"Error sending error message to the log channel: {e.message}")


async def bad_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Raise an error to trigger the error handler."""
    await context.bot.wrong_method_name()  # type: ignore[attr-defined]


def main():
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    application = (
        ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).concurrent_updates(True).build()
    )

    # Define handlers
    start_handler = CommandHandler(
        "start",
        lambda update, context: start(update, context),
    )
    photo_handler = MessageHandler(
        filters.PHOTO,
        lambda update, context: photo(update, context),
    )
    help_handler = CommandHandler("help", help)
    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, message)
    bad_command_handler = CommandHandler("bad_command", bad_command)

    # Register handlers
    application.add_handler(help_handler)
    application.add_handler(message_handler)
    application.add_handler(photo_handler)
    application.add_handler(bad_command_handler)
    application.add_error_handler(error)
    application.add_handler(start_handler)

    # Run the bot in polling mode or webhook mode depending on the environment
    PRODUCTION = os.environ.get("PRODUCTION", False) == "True"
    if PRODUCTION:
        application.run_webhook()
    else:
        application.run_polling()


if __name__ == "__main__":
    main()
