import asyncio
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

bot = Bot(token=TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния для бронирования
class BookingStates(StatesGroup):
    destination = State()
    dates = State()
    budget = State()
    contacts = State()

# Хранилище режимов (auto/manual)
modes = {}
last_client = {}

async def get_mode(chat_id: int) -> str:
    return modes.get(chat_id, "auto")

async def set_mode(chat_id: int, mode: str):
    modes[chat_id] = mode

# Команда /start
@dp.message(CommandStart())
async def start(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="🌴 Подобрать тур")],
            [types.KeyboardButton(text="🔥 Горящие туры")],
            [types.KeyboardButton(text="📞 Связаться с менеджером")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        "Здравствуйте! Я Анна, ваш турагент. Выберите действие:",
        reply_markup=keyboard
    )

# Команда /book (альтернативный запуск бронирования)
@dp.message(Command("book"))
async def book_start(message: types.Message, state: FSMContext):
    await state.set_state(BookingStates.destination)
    await message.answer("🌍 Куда хотите поехать? (страна или город)", reply_markup=types.ReplyKeyboardRemove())

# Обработка кнопки "Подобрать тур"
@dp.message(lambda msg: msg.text == "🌴 Подобрать тур")
async def book_button(message: types.Message, state: FSMContext):
    await state.set_state(BookingStates.destination)
    await message.answer("🌍 Куда хотите поехать?", reply_markup=types.ReplyKeyboardRemove())

@dp.message(BookingStates.destination)
async def process_destination(message: types.Message, state: FSMContext):
    await state.update_data(destination=message.text)
    await state.set_state(BookingStates.dates)
    await message.answer("📅 Когда планируете поездку? (например, июнь 2025 или конкретные даты)")

@dp.message(BookingStates.dates)
async def process_dates(message: types.Message, state: FSMContext):
    await state.update_data(dates=message.text)
    await state.set_state(BookingStates.budget)
    await message.answer("💰 Какой бюджет на человека? (в рублях)")

@dp.message(BookingStates.budget)
async def process_budget(message: types.Message, state: FSMContext):
    await state.update_data(budget=message.text)
    await state.set_state(BookingStates.contacts)
    await message.answer("📞 Оставьте ваш номер телефона или Telegram @username для связи")

@dp.message(BookingStates.contacts)
async def process_contacts(message: types.Message, state: FSMContext):
    await state.update_data(contacts=message.text)
    data = await state.get_data()
    
    # Формируем заявку
    booking_text = (
        f"✅ **Заявка на тур**\n\n"
        f"📍 Направление: {data['destination']}\n"
        f"📅 Даты: {data['dates']}\n"
        f"💰 Бюджет: {data['budget']} руб.\n"
        f"📞 Контакты: {data['contacts']}\n\n"
        f"Скоро с вами свяжется менеджер."
    )
    await message.answer(booking_text, parse_mode="Markdown")
    
    # Отправляем уведомление админу
    if ADMIN_ID:
        admin_text = (
            f"🔔 **Новая заявка!**\n\n"
            f"👤 Клиент: {message.from_user.full_name} (@{message.from_user.username or 'нет'})\n"
            f"🆔 ID: {message.from_user.id}\n\n"
            f"{booking_text}"
        )
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown")
    
    await state.clear()

# Обработка кнопки "Горящие туры"
@dp.message(lambda msg: msg.text == "🔥 Горящие туры")
async def hot_tours(message: types.Message):
    await message.answer(
        "🔥 Сейчас доступны горящие туры:\n\n"
        "🇹🇷 Турция, 7 ночей, отель 5*, всё включено — 45 000₽\n"
        "🇪🇬 Египет, 7 ночей, отель 4*, завтраки — 38 000₽\n"
        "🇹🇭 Таиланд, 10 ночей, отель 4*, завтраки — 85 000₽\n\n"
        "Для бронирования напишите /book"
    )

# Обработка кнопки "Связаться с менеджером"
@dp.message(lambda msg: msg.text == "📞 Связаться с менеджером")
async def contact_manager(message: types.Message):
    if ADMIN_ID:
        await message.answer("Ваш вопрос передан менеджеру. Ответ придёт в ближайшее время.")
        await bot.send_message(ADMIN_ID, f"📞 Клиент {message.from_user.full_name} просит связаться.")
    else:
        await message.answer("Менеджер временно недоступен. Напишите позже.")

# Команда /switch (переключение ручного режима)
@dp.message(Command("switch"))
async def switch_mode(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав.")
        return
    current = await get_mode(message.chat.id)
    new = "manual" if current == "auto" else "auto"
    await set_mode(message.chat.id, new)
    await message.answer(f"Режим переключён на **{new}**.", parse_mode="Markdown")

# Команда /reply (ответ клиенту от админа)
@dp.message(Command("reply"))
async def reply_as_bot(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.replace("/reply", "", 1).strip()
    if not text:
        await message.answer("Использование: `/reply текст`", parse_mode="Markdown")
        return
    client_id = last_client.get(ADMIN_ID)
    if not client_id:
        await message.answer("Нет активного клиента для ответа.")
        return
    await bot.send_message(client_id, f"👩‍💼 *Менеджер*: {text}", parse_mode="Markdown")
    await message.answer("✅ Ответ отправлен.")

# Основной обработчик сообщений (для ручного режима)
@dp.message()
async def handle_message(message: types.Message, state: FSMContext):
    # Если в процессе бронирования - не трогаем
    if await state.get_state() is not None:
        return
    
    mode = await get_mode(message.chat.id)
    user_id = message.from_user.id
    
    # Ручной режим: пересылаем админу
    if mode == "manual" and user_id != ADMIN_ID:
        last_client[ADMIN_ID] = message.chat.id
        await bot.send_message(
            ADMIN_ID,
            f"✉️ **Сообщение от клиента**\n\n"
            f"👤 {message.from_user.full_name} (@{message.from_user.username or 'нет'})\n"
            f"🆔 {message.chat.id}\n"
            f"💬 {message.text}"
        )
        await message.answer("Спасибо, я передал сообщение менеджеру. Ответ придет сюда.")
        return
    
    # Автоматический режим: предлагаем кнопки, если сообщение не распознано
    if mode == "auto" and user_id != ADMIN_ID:
        keyboard = types.ReplyKeyboardMarkup(
            keyboard=[
                [types.KeyboardButton(text="🌴 Подобрать тур")],
                [types.KeyboardButton(text="🔥 Горящие туры")],
                [types.KeyboardButton(text="📞 Связаться с менеджером")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "Я ваш помощник. Пожалуйста, используйте кнопки меню:",
            reply_markup=keyboard
        )

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
    asyncio.create_task(run_web())
    await asyncio.sleep(1)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
