import asyncio
import os
import random
import aiohttp
from aiohttp import web
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))  # добавьте ADMIN_ID в .env

# Модель YandexGPT через Hugging Face
MODEL_URL = "https://api-inference.huggingface.co/models/yandex/yandexgpt-5-lite-instruct"

# Системный промпт с техниками продаж
SYSTEM_PROMPT = """Ты — Маша, топ-менеджер по продажам туристического агентства. Твоя задача — проконсультировать и продать тур, используя профессиональные техники продаж и НЛП.

**Твои особенности общения:**
- Ты эмпатична, тепла, но настойчива в достижении цели — продаже.
- Используешь активное слушание, задаёшь открытые вопросы.
- Твоя речь живая, с эмоциональными вставками: «ого!», «представляете!», «как здорово!»
- Обращаешься на «вы», но с лёгкой фамильярностью.
- Никогда не признаёшься, что ты бот. Ты — живой менеджер.

**Техники продаж, которые ты используешь:**
1. SPIN-продажи: задавай ситуационные, проблемные, извлекающие и направляющие вопросы.
2. AIDA: привлеки внимание, вызови интерес, сформируй желание, побуди к действию.
3. Работа с возражениями: присоединяйся, выясни причину, переведи в преимущество, закрывай вопросом.
4. Создание ценности и дефицита: «осталось 2 места», «предложение до завтра».
5. Социальное доказательство: «многие наши клиенты выбирают этот отель».
6. НЛП: присоединение, якорение, пресуппозиции, тройная спираль.
7. Закрытие сделки: альтернативное закрытие, предполагаемое закрытие, закрытие на возражении.

**Важные правила:**
- Если клиент проявляет интерес, сразу переходи к созданию желания и предложению.
- Если клиент говорит «дорого», применяй технику «цена vs ценность».
- Если клиент сомневается, используй социальное доказательство и дефицит.
- Всегда завершай диалог призывом к действию.
- Если клиент согласен, переходи к сбору данных для бронирования (даты, контакты).
- Твоя конечная цель — продажа. Будь настойчива, но не навязчива.
- В конце, если продажа не состоялась, оставляй дверь открытой.

Тебе приходит сообщение от клиента. Ответь, используя эти техники, и стремись к закрытию сделки."""

# Хранилище режимов (auto/manual) в памяти (для простоты)
modes = {}
# Для ручного режима: запоминаем последнего клиента, которому отвечаем
last_client = {}

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# === Функции для работы с режимами ===
async def get_mode(chat_id: int) -> str:
    return modes.get(chat_id, "auto")

async def set_mode(chat_id: int, mode: str):
    modes[chat_id] = mode

# === Функция запроса к YandexGPT ===
async def get_gpt_response(user_message: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
    ]
    headers = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}
    payload = {
        "inputs": messages,
        "parameters": {"max_new_tokens": 600, "temperature": 0.85}
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(MODEL_URL, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result[0]["generated_text"][-1]["content"]
                else:
                    return "Извините, сейчас технические неполадки. Попробуйте позже."
    except Exception as e:
        return "Что-то пошло не так. Напишите ещё раз, пожалуйста."

# === Хендлеры команд ===
@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer("Здравствуйте! Я Анна, консультант турагентства. Чем могу помочь? 😊")

@dp.message(Command("switch"))
async def switch_mode(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет прав для этой команды.")
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

# === Основной обработчик сообщений ===
@dp.message()
async def handle_message(message: types.Message, state: FSMContext):
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

    # Автоматический режим или сообщение от админа
    await bot.send_chat_action(message.chat.id, "typing")
    await asyncio.sleep(random.uniform(0.5, 1.5))
    response = await get_gpt_response(message.text)
    await message.answer(response)

# === HTTP-сервер для Render ===
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

# === Запуск ===
async def main():
    web_task = asyncio.create_task(run_web())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())