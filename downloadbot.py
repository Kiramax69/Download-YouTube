import logging
import os
import yt_dlp
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Конфигурация
TOKEN = "7787818513:AAEZwJ-6tl1B7NN_GdgL0P1GqXWiqVKLEBU"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 МБ для обычных пользователей Telegram
TEMP_DIR = "temp_downloads"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Создаем временную папку если не существует
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

async def on_startup(_):
    logger.info("Бот успешно запущен!")

@dp.message(commands=['start', 'help'])
async def start_command(message: types.Message):
    """Обработчик команды /start"""
    welcome_text = (
        "Привет! Я бот для скачивания видео с YouTube.\n"
        "Просто отправь мне ссылку на видео, и я предложу варианты загрузки.\n"
        "Ограничения: видео до 50 МБ (Telegram лимит)"
    )
    await message.answer(welcome_text)

@dp.message(content_types=['text'])
async def process_link(message: types.Message):
    """Обработка ссылок на видео"""
    url = message.text.strip()
    
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestvideo+bestaudio/best",
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get("formats", [])
            title = info.get("title", "Video")

        keyboard = InlineKeyboardMarkup(row_width=2)
        quality_options = {}

        for f in formats:
            if f.get("vcodec") != "none" and f.get("acodec") != "none":
                res = f.get("format_note", "Unknown")
                file_size = f.get("filesize") or f.get("filesize_approx") or 0
                
                if file_size and file_size <= MAX_FILE_SIZE:
                    quality_options[res] = f["format_id"]

        if not quality_options:
            await message.answer(
                "Видео слишком большое (>50МБ) или нет подходящих форматов.\n"
                "Попробуйте другое видео."
            )
            return

        for res, format_id in quality_options.items():
            button = InlineKeyboardButton(
                text=f"{res}",
                callback_data=f"video|{url}|{format_id}"
            )
            keyboard.insert(button)

        audio_button = InlineKeyboardButton(
            text="🎵 Только аудио (MP3)",
            callback_data=f"audio|{url}"
        )
        keyboard.add(audio_button)

        await message.answer(
            f"Видео: {title}\nВыберите качество:",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка обработки ссылки: {e}")
        await message.answer("Ошибка: неверная ссылка или видео недоступно")

@dp.callback_query(lambda c: c.data.startswith(("video|", "audio|")))
async def process_download(callback: types.CallbackQuery):
    """Обработка скачивания видео или аудио"""
    await bot.answer_callback_query(callback.id)
    
    data = callback.data.split("|")
    download_type, url = data[0], data[1]
    format_id = data[2] if download_type == "video" else "bestaudio"
    
    user_id = callback.from_user.id
    file_ext = "mp3" if download_type == "audio" else "mp4"
    filename = os.path.join(TEMP_DIR, f"{user_id}_{format_id}.{file_ext}")

    ydl_opts = {
        "outtmpl": filename,
        "quiet": True,
        "format": format_id,
        "merge_output_format": "mp4",
    }
    
    if download_type == "audio":
        ydl_opts.update({
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        })

    progress_msg = await bot.send_message(user_id, "⏳ Скачивание началось...")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        file_size = os.path.getsize(filename)
        if file_size > MAX_FILE_SIZE:
            await progress_msg.edit_text("❌ Файл слишком большой для отправки")
            os.remove(filename)
            return

        await progress_msg.edit_text("✅ Загрузка файла в Telegram...")
        
        with open(filename, "rb") as file:
            if download_type == "audio":
                await bot.send_audio(user_id, file)
            else:
                await bot.send_video(user_id, file)

        await progress_msg.delete()

    except Exception as e:
        logger.error(f"Ошибка скачивания: {e}")
        await progress_msg.edit_text("❌ Ошибка при скачивании")

    finally:
        if os.path.exists(filename):
            os.remove(filename)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
