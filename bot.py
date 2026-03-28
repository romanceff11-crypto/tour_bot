import asyncio
import os
import random
import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiohttp import web

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

print(f"TELEGRAM_TOKEN: {'OK' if TELEGRAM_TOKEN else 'MISSING'}")
print(f"HUGGINGFACE_TOKEN: {'OK' if HUGGINGFACE_TOKEN else 'MISSING'}")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Используем модель Google Gemma 2 9B Instruct
MODEL_URL = "https://api-inference.huggingface.co/models/google/gemma-2-9b-it"

SYSTEM_PROMPT = """Ты — Анна, топ-менеджер по продажам туристического агентства. Твоя задача — продать тур, используя профессиональные техники продаж и НЛП.

Ты общаешься тепло, заботливо, немного эмоционально. Используешь активное слушание, задаёшь открытые вопросы. Обращаешься на «вы», но с лёгкой фамильярностью (как к хорошему знакомому). Никогда не признаёшься, что ты бот. Ты — живой менеджер.

Используй техники: SPIN-продажи, AIDA, работа с возражениями, создание ценности и дефицита, социальное доказательство, НЛП-якорение, закрытие сделки.

Всегда стремись к продаже. Если клиент проявляет интерес, сразу переходи к предложению. При возражениях применяй технику «цена vs ценность». Завершай диалог призывом к действию.

Твоя цель — помочь клиенту выбрать тур и оформить бронь."""

modes = {}
last_client = {}

async def get_mode(chat_id: int) -> str:
    return modes.get(chat_id, "auto")

async def set_mode(chat_id: int, mode: str):
    modes[chat_id] = mode

async def get_gpt_response(user_message: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
    ]
    headers = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}
    payload = {
        "inputs": messages,
        "parameters": {"max_new_tokens": 500, "temperature": 0.85, "top_p": 0.95}
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(MODEL_URL, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    if isinstance(result, list) and len(result) > 0:
                        generated = result[0].get("generated_text", [])
                        if generated and isinstance(generated, list):
                            for msg in reversed(generated):
                                if msg.get("role") == "assistant":
                                    return msg.get("content", "Извините, не удалось сформулировать ответ.")
                    return "Извините, не удалось обработать запрос."
                else:
                    error_text = await resp.text()
                    print(f"❌ Hugging Face API error {resp.status}: {error_text[:200]}")
                    return f"Извините, сейчас технические неполадки (код {resp.status}). Попробуйте позже."
    except Exception as e:
        print(f"❌ Exception in GPT: {type(e).__name__}: {e}")
        return "Извините, сейчас технические неполадки. Попробуйте позже."

@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer("Здравствуйте! Я Анна, консультант турагентства. Чем могу помочь? 😊")

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer("Просто задайте вопрос о путешествиях, и я помогу подобрать тур!")

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
    client_chat_id = last_client.get(ADMIN_ID)
    if not client_chat_id:
        await message.answer("Нет активного клиента для ответа.")
        return
    await bot.send_message(client_chat_id, f"👩‍💼 (Менеджер): {text}")
    await message.answer("Ответ отправлен.")

@dp.message()
async def handle_message(message: types.Message):
    mode = await get_mode(message.chat.id)
    user_id = message.from_user.id

    if mode == "manual" and user_id != ADMIN_ID:
        last_client[ADMIN_ID] = message.chat.id
        await bot.send_message(
            ADMIN_ID,
            f"✉️ Сообщение от клиента (чат {message.chat.id}):\n{message.text}"
        )
        await message.answer("Спасибо, ваш вопрос передан менеджеру. Ответ придёт в ближайшее время.")
        return

    await bot.send_chat_action(message.chat.id, "typing")
    await asyncio.sleep(random.uniform(0.5, 1.5))
    response = await get_gpt_response(message.text)
    await message.answer(response)

# HTTP-сервер для Render
async def health(request):
    return web.Response(text="OK")

async def run_web():
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"HTTP server started on port {port}")
    await asyncio.Event().wait()

async def main():
    web_task = asyncio.create_task(run_web())
    await asyncio.sleep(2)   # даём серверу время запуститься
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())