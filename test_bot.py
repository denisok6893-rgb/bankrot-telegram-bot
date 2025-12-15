import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

BOT_TOKEN = "8460225301:AAGa8wP1sm68NGl2AUDALVkQBYoFGdthrKo"

dp = Dispatcher()

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("Я живой. Python-бот работает на сервере.")

async def main():
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
