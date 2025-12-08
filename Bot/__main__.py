import asyncio
from Bot.bot import dp, bot  # <-- your actual paths
from aiogram.exceptions import TelegramNetworkError, TelegramAPIError

async def start():
    while True:
        try:
            print("Bot polling started...")
            await dp.start_polling(bot)

        except TelegramNetworkError as e:
            print(f"Network error: {e}")
            await asyncio.sleep(3)

        except TelegramAPIError as e:
            print(f"Telegram API error: {e}")
            await asyncio.sleep(3)

        except Exception as e:
            print(f"Unexpected error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(start())
