import asyncio
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer("Привет! Я бот-эхо. Напиши что-нибудь.")

@dp.message()
async def echo(message: types.Message):
    await message.answer(f"Вы сказали: {message.text}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())