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

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

logger.info(f"TELEGRAM_TOKEN: {'✅' if TELEGRAM_TOKEN else '❌'}")
logger.info(f"GIGACHAT_CREDENTIALS: {'✅' if GIGACHAT_CREDENTIALS else '❌'}")
logger.info(f"ADMIN_ID: {ADMIN_ID}")

# === ИНИЦИАЛИЗАЦИЯ БОТА ===
bot = Bot(token=TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# === СОСТОЯНИЯ ДЛЯ БРОНИРОВАНИЯ (FSM) ===
class BookingStates(StatesGroup):
    destination = State()   # направление
    dates = State()         # даты
    budget = State()        # бюджет
    contacts = State()      # контакты

# === СИСТЕМНЫЙ ПРОМПТ С ТЕХНИКАМИ ПРОДАЖ ===
SYSTEM_PROMPT = """Ты — Анна, топ-менеджер по продажам туристического агентства. Твоя задача — продать тур.

Ты общаешься тепло, заботливо, немного эмоционально. Используешь активное слушание, задаёшь открытые вопросы. Обращаешься на «вы». Никогда не признаёшься, что ты бот.

Используй техники продаж: задавай вопросы о желаниях клиента, предлагай подходящие варианты, работай с возражениями, создавай ценность. Всегда стремись к продаже.

Твоя цель — помочь клиенту выбрать тур и оформить бронь."""

# === ХРАНИЛИЩЕ РЕЖИМОВ (auto/manual) ===
modes = {}
last_client = {}

async def get_mode(chat_id: int) -> str:
    return modes.get(chat_id, "auto")

async def set_mode(chat_id: int, mode: str):
    modes[chat_id] = mode

# === ФУНКЦИЯ ЗАПРОСА К GigaChat ===
async def get_giga_response(user_message: str) -> str:
    """Отправляет запрос к GigaChat и возвращает ответ"""
    try:
        # Создаём клиент GigaChat (контекстный менеджер сам закроет соединение)
        with GigaChat(
            credentials=GIGACHAT_CREDENTIALS,
            verify_ssl_certs=False,        # Для работы на Render (отключаем проверку сертификатов)
            scope="GIGACHAT_API_PERS",      # Для физических лиц
            model="GigaChat-2",             # Модель второго поколения
            temperature=0.85,
            max_tokens=500,
            timeout=30.0
        ) as giga:
            # Формируем сообщения в правильном формате
            messages = [
                Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT),
                Messages(role=MessagesRole.USER, content=user_message)
            ]
            
            # Отправляем запрос
            chat = Chat(messages=messages)
            response = giga.chat(chat)
            
            # Извлекаем текст ответа
            if response.choices and len(response.choices) > 0:
                return response.choices[0].message.content
            else:
                return "Извините, не удалось получить ответ от сервиса."
                
    except Exception as e:
        logger.error(f"Ошибка GigaChat: {type(e).__name__}: {e}")
        return "Извините, сейчас технические неполадки. Попробуйте позже."

# === КОМАНДЫ ===
@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "Здравствуйте! Я Анна, консультант турагентства. Чем могу помочь? 😊\n\n"
        "Доступные команды:\n"
        "/book — начать бронирование тура\n"
        "/help — помощь"
    )

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "Я помогу вам подобрать и забронировать тур.\n\n"
        "📌 Команды:\n"
        "/start — начать диалог\n"
        "/book — начать процесс бронирования\n"
        "/switch — переключить ручной режим (только для администратора)\n\n"
        "Просто напишите, куда хотите поехать, и я подберу варианты!"
    )

@dp.message(Command("book"))
async def book_start(message: types.Message, state: FSMContext):
    await state.set_state(BookingStates.destination)
    await message.answer("📍 Куда хотели бы поехать? (страна, город или курорт)")

@dp.message(BookingStates.destination)
async def book_destination(message: types.Message, state: FSMContext):
    await state.update_data(destination=message.text)
    await state.set_state(BookingStates.dates)
    await message.answer("📅 Когда планируете поездку? (укажите примерные даты или месяц)")

@dp.message(BookingStates.dates)
async def book_dates(message: types.Message, state: FSMContext):
    await state.update_data(dates=message.text)
    await state.set_state(BookingStates.budget)
    await message.answer("💰 Какой бюджет на человека? (в рублях)")

@dp.message(BookingStates.budget)
async def book_budget(message: types.Message, state: FSMContext):
    await state.update_data(budget=message.text)
    await state.set_state(BookingStates.contacts)
    await message.answer("📞 Оставьте ваш номер телефона или Telegram @username для связи")

@dp.message(BookingStates.contacts)
async def book_contacts(message: types.Message, state: FSMContext):
    await state.update_data(contacts=message.text)
    data = await state.get_data()
    
    # Формируем сообщение с заявкой
    booking_text = (
        f"✅ **Заявка на бронирование принята!**\n\n"
        f"📍 Направление: {data['destination']}\n"
        f"📅 Даты: {data['dates']}\n"
        f"💰 Бюджет: {data['budget']} руб.\n"
        f"📞 Контакты: {data['contacts']}\n\n"
        f"Менеджер свяжется с вами в ближайшее время."
    )
    await message.answer(booking_text, parse_mode="Markdown")
    
    # Отправляем уведомление админу (если задан)
    if ADMIN_ID:
        admin_text = (
            f"🔔 **Новая заявка на бронирование!**\n\n"
            f"От: @{message.from_user.username or message.from_user.first_name}\n"
            f"ID: {message.from_user.id}\n\n"
            f"{booking_text}"
        )
        try:
            await bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу: {e}")
    
    await state.clear()

@dp.message(Command("switch"))
async def switch_mode(message: types.Message):
    """Переключение между автоматическим и ручным режимом (только админ)"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return
    
    current = await get_mode(message.chat.id)
    new_mode = "manual" if current == "auto" else "auto"
    await set_mode(message.chat.id, new_mode)
    await message.answer(
        f"🔄 Режим работы изменён: **{new_mode}**\n"
        f"{'🤖 Бот отвечает автоматически' if new_mode == 'auto' else '👤 Сообщения пересылаются менеджеру'}",
        parse_mode="Markdown"
    )

@dp.message(Command("reply"))
async def reply_as_bot(message: types.Message):
    """Ответить клиенту от имени бота (только админ)"""
    if message.from_user.id != ADMIN_ID:
        return
    
    text = message.text.replace("/reply", "", 1).strip()
    if not text:
        await message.answer("ℹ️ Использование: `/reply Текст ответа`", parse_mode="Markdown")
        return
    
    client_chat_id = last_client.get(ADMIN_ID)
    if not client_chat_id:
        await message.answer("❌ Нет активного клиента для ответа.")
        return
    
    try:
        await bot.send_message(client_chat_id, f"👩‍💼 *Менеджер*: {text}", parse_mode="Markdown")
        await message.answer("✅ Ответ отправлен клиенту.")
    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке: {e}")

# === ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ===
@dp.message()
async def handle_message(message: types.Message, state: FSMContext):
    """Обрабатывает все текстовые сообщения"""
    # Если пользователь в процессе бронирования — не трогаем, FSM сам обработает
    current_state = await state.get_state()
    if current_state is not None:
        return
    
    mode = await get_mode(message.chat.id)
    user_id = message.from_user.id
    
    # Ручной режим: пересылаем сообщение админу
    if mode == "manual" and user_id != ADMIN_ID:
        last_client[ADMIN_ID] = message.chat.id
        await bot.send_message(
            ADMIN_ID,
            f"✉️ **Новое сообщение от клиента**\n\n"
            f"👤 {message.from_user.full_name} (@{message.from_user.username or 'нет username'})\n"
            f"🆔 {message.chat.id}\n"
            f"💬 {message.text}"
        )
        await message.answer(
            "🙂 Спасибо за сообщение! Я передал его менеджеру. "
            "Обычно ответ приходит в течение нескольких минут."
        )
        return
    
    # Автоматический режим: отвечаем через GigaChat
    try:
        # Эмуляция набора текста
        await bot.send_chat_action(message.chat.id, "typing")
        await asyncio.sleep(random.uniform(0.5, 1.0))
        
        response = await get_giga_response(message.text)
        await message.answer(response)
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}")
        await message.answer("Извините, произошла ошибка. Пожалуйста, попробуйте позже.")

# === HTTP-СЕРВЕР ДЛЯ RENDER ===
async def health_check(request):
    """Эндпоинт для проверки работоспособности"""
    return web.Response(text="OK")

async def run_web_server():
    """Запускает HTTP-сервер, чтобы Render не отключал бота"""
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    logger.info(f"🌐 HTTP-сервер запущен на порту {port}")
    
    # Бесконечно ждём
    await asyncio.Event().wait()

# === ТОЧКА ВХОДА ===
async def main():
    # Запускаем HTTP-сервер в фоне
    web_task = asyncio.create_task(run_web_server())
    # Даём время серверу запуститься
    await asyncio.sleep(1)
    # Запускаем бота
    logger.info("🤖 Бот запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())