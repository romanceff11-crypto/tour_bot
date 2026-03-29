import asyncio
import os
import random
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from gigachat import GigaChat
from gigachat.models import Chat, Messages, Message

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GIGACHAT_CLIENT_ID = os.getenv("GIGACHAT_CLIENT_ID")
GIGACHAT_SECRET = os.getenv("GIGACHAT_SECRET")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

print(f"TELEGRAM_TOKEN: {'OK' if TELEGRAM_TOKEN else 'MISSING'}")
print(f"GIGACHAT_CLIENT_ID: {'OK' if GIGACHAT_CLIENT_ID else 'MISSING'}")
print(f"GIGACHAT_SECRET: {'OK' if GIGACHAT_SECRET else 'MISSING'}")

bot = Bot(token=TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния для бронирования
class BookingStates(StatesGroup):
    destination = State()
    dates = State()
    budget = State()
    contacts = State()

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

# Функция для получения ответа от GigaChat (с автоматическим обновлением токена)
async def get_giga_response(user_message: str) -> str:
    try:
        # Создаём клиент с client_id и secret — токен будет получаться автоматически
        with GigaChat(
            client_id=GIGACHAT_CLIENT_ID,
            client_secret=GIGACHAT_SECRET,
            verify_ssl_certs=False,
            scope="GIGACHAT_API_PERS",
            model="GigaChat-2",
            temperature=0.85,
            max_tokens=500
        ) as giga:
            messages = [
                Message(role="system", content=SYSTEM_PROMPT),
                Message(role="user", content=user_message)
            ]
            response = giga.chat(Chat(messages=messages))
            return response.choices[0].message.content
    except Exception as e:
        print(f"❌ GigaChat error: {type(e).__name__}: {e}")
        return "Извините, сейчас технические неполадки. Попробуйте позже."

# Остальные хендлеры (start, help, book, switch, reply, handle_message) такие же, как в предыдущем коде
# Я их не повторяю для краткости, но они полностью совместимы.

# ... (вставьте сюда все хендлеры из предыдущего сообщения, они не изменились)

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
    await asyncio.sleep(2)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())