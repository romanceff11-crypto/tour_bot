import asyncio
import os
import random
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

logger.info(f"TELEGRAM_TOKEN: {'✅' if TELEGRAM_TOKEN else '❌'}")
logger.info(f"GIGACHAT_CREDENTIALS: {'✅' if GIGACHAT_CREDENTIALS else '❌'}")

bot = Bot(token=TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class BookingStates(StatesGroup):
    destination = State()
    dates = State()
    budget = State()
    contacts = State()

SYSTEM_PROMPT = """Ты — Анна, топ-менеджер по продажам туристического агентства. Твоя задача — продать тур, используя профессиональные техники продаж и НЛП.

Ты общаешься тепло, заботливо, немного эмоционально. Используешь активное слушание, задаёшь открытые вопросы. Обращаешься на «вы». Никогда не признаёшься, что ты бот.

Используй техники: SPIN-продажи, AIDA, работа с возражениями, создание ценности и дефицита, социальное доказательство, НЛП-якорение, закрытие сделки.

Всегда стремись к продаже. Если клиент проявляет интерес, сразу переходи к предложению. При возражениях применяй технику «цена vs ценность». Завершай диалог призывом к действию."""

modes = {}
last_client = {}

async def get_mode(chat_id: int) -> str:
    return modes.get(chat_id, "auto")

async def set_mode(chat_id: int, mode: str):
    modes[chat_id] = mode

async def get_giga_response(user_message: str) -> str:
    try:
        with GigaChat(
            credentials=GIGACHAT_CREDENTIALS,
            verify_ssl_certs=False,
            scope="GIGACHAT_API_PERS",
            model="GigaChat-2",
            temperature=0.85,
            max_tokens=500,
            timeout=30.0
        ) as giga:
            messages = [
                Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT),
                Messages(role=MessagesRole.USER, content=user_message)
            ]
            chat = Chat(messages=messages)
            response = giga.chat(chat)
            if response.choices and len(response.choices) > 0:
                return response.choices[0].message.content
            return "Извините, не удалось получить ответ от сервиса."
    except Exception as e:
        logger.error(f"Ошибка GigaChat: {type(e).__name__}: {e}")
        return "Извините, сейчас технические неполадки. Попробуйте позже."

@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer("Здравствуйте! Я Анна, консультант турагентства. Чем могу помочь? 😊")

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer("Команды:\n/book – начать бронирование\n/switch – ручной режим\n/reply – ответ клиенту")

@dp.message(Command("book"))
async def book_start(message: types.Message, state: FSMContext):
    await state.set_state(BookingStates.destination)
    await message.answer("Куда хотели бы поехать? (страна или курорт)")

@dp.message(BookingStates.destination)
async def book_destination(message: types.Message, state: FSMContext):
    await state.update_data(destination=message.text)
    await state.set_state(BookingStates.dates)
    await message.answer("Когда планируете поездку? (даты или месяц)")

@dp.message(BookingStates.dates)
async def book_dates(message: types.Message, state: FSMContext):
    await state.update_data(dates=message.text)
    await state.set_state(BookingStates.budget)
    await message.answer("Какой бюджет на человека? (в рублях)")

@dp.message(BookingStates.budget)
async def book_budget(message: types.Message, state: FSMContext):
    await state.update_data(budget=message.text)
    await state.set_state(BookingStates.contacts)
    await message.answer("Оставьте ваш номер телефона или Telegram @username")

@dp.message(BookingStates.contacts)
async def book_contacts(message: types.Message, state: FSMContext):
    await state.update_data(contacts=message.text)
    data = await state.get_data()
    await message.answer(
        f"✅ Заявка принята!\n\n"
        f"📍 Направление: {data['destination']}\n"
        f"📅 Даты: {data['dates']}\n"
        f"💰 Бюджет: {data['budget']} руб.\n"
        f"📞 Контакты: {data['contacts']}\n\n"
        f"Менеджер свяжется с вами."
    )
    if ADMIN_ID:
        await bot.send_message(ADMIN_ID, f"🔔 Новая заявка!\n{data}")
    await state.clear()

@dp.message(Command("switch"))
async def switch_mode(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав.")
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
        await message.answer("Использование: `/reply Текст`", parse_mode="Markdown")
        return
    client_id = last_client.get(ADMIN_ID)
    if not client_id:
        await message.answer("Нет активного клиента.")
        return
    await bot.send_message(client_id, f"👩‍💼 *Менеджер*: {text}", parse_mode="Markdown")
    await message.answer("✅ Ответ отправлен.")

@dp.message()
async def handle_message(message: types.Message, state: FSMContext):
    if await state.get_state() is not None:
        return
    mode = await get_mode(message.chat.id)
    user_id = message.from_user.id

    if mode == "manual" and user_id != ADMIN_ID:
        last_client[ADMIN_ID] = message.chat.id
        await bot.send_message(ADMIN_ID, f"✉️ Сообщение от {message.chat.id}:\n{message.text}")
        await message.answer("Спасибо, вопрос передан менеджеру.")
        return

    await bot.send_chat_action(message.chat.id, "typing")
    await asyncio.sleep(random.uniform(0.5, 1.0))
    response = await get_giga_response(message.text)
    await message.answer(response)

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
    logger.info(f"HTTP сервер запущен на порту {port}")
    await asyncio.Event().wait()

async def main():
    web_task = asyncio.create_task(run_web())
    await asyncio.sleep(1)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())