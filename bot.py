import asyncio
import os
import random
import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
ADMIN_ID = int(os.getenv("Transneft_Ufa", 0))  # если не задан, то 0 — команды не сработают

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Хранилище режимов (в памяти)
modes = {}  # chat_id -> "auto" / "manual"
last_client = {}  # для ручного ответа: {admin_id: client_chat_id}

MODEL_URL = "https://api-inference.huggingface.co/models/yandex/yandexgpt-5-lite-instruct"

SYSTEM_PROMPT = """Ты — Анна, консультант туристического агентства. Ты общаешься тепло, заботливо, немного эмоционально. Обращаешься на «вы». Используй эмодзи умеренно. Никогда не признавайся, что ты бот. Ты — сотрудник турагентства Анна."""

async def get_gpt_response(user_message: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
    ]
    headers = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}
    payload = {
        "inputs": messages,
        "parameters": {"max_new_tokens": 300, "temperature": 0.8}
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(MODEL_URL, headers=headers, json=payload) as resp:
            if resp.status == 200:
                result = await resp.json()
                return result[0]["generated_text"][-1]["content"]
            else:
                return "Извините, сейчас большая нагрузка. Попробуйте позже."

async def get_mode(chat_id: int) -> str:
    return modes.get(chat_id, "auto")

async def set_mode(chat_id: int, mode: str):
    modes[chat_id] = mode

@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer("Здравствуйте! Я Анна, консультант турагентства. Чем могу помочь? 😊")

@dp.message(Command("switch"))
async def switch_mode(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет прав.")
        return
    current = await get_mode(message.chat.id)
    new = "manual" if current == "auto" else "auto"
    await set_mode(message.chat.id, new)
    await message.answer(f"Режим переключён на **{new}**.", parse_mode="Markdown")

@dp.message(Command("reply"))
async def reply_as_bot(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.replace("/reply", "", 1).strip()
    if not text:
        await message.answer("Напишите текст после /reply")
        return
    client_id = last_client.get(message.chat.id)
    if not client_id:
        await message.answer("Нет активного клиента для ответа.")
        return
    await bot.send_message(client_id, f"👩‍💼 (Менеджер): {text}")
    await message.answer("Ответ отправлен.")

@dp.message()
async def handle_message(message: types.Message):
    mode = await get_mode(message.chat.id)
    user_id = message.from_user.id

    # Ручной режим: пересылаем админу
    if mode == "manual" and user_id != ADMIN_ID:
        last_client[ADMIN_ID] = message.chat.id
        await bot.send_message(
            ADMIN_ID,
            f"✉️ Сообщение от клиента (чат {message.chat.id}):\n{message.text}"
        )
        await message.answer("Спасибо, ваш вопрос передан менеджеру. Ответ придёт в ближайшее время.")
        return

    # Автоматический режим: отвечаем через GPT
    await bot.send_chat_action(message.chat.id, "typing")
    await asyncio.sleep(random.uniform(0.5, 1.5))
    response = await get_gpt_response(message.text)
    await message.answer(response)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())