from clients import send_main_menu, send_telegram_request
from constants import GREETINGS_PROMPT_SHORT

async def send_default_main_menu(chat_id: int) -> None:
    """
    Sends the default main menu to the user.
    """
    await send_main_menu(chat_id, GREETINGS_PROMPT_SHORT)

async def send_db_error_message(chat_id: int, error_message: str) -> None:
    """
    Sends a generic database error message.
    """
    await send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": error_message,
    })
