import logging
import os
import yt_dlp
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage

# Токен Telegram-бота
TOKEN = "7787818513:AAEZwJ-6tl1B7NN_GdgL0P1GqXWiqVKLEBU"

# Настройка бота
bot = Bot(token=TOKEN)
storage = MemoryStorage()  # Используем память для хранения состояний
dp = Dispatcher(bot, storage=storage)  # Передаем bot в Dispatcher через параметр storage

# Логирование
logging.basicConfig(level=logging.INFO)

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer("Привет! Отправь мне ссылку на видео с YouTube, и я помогу тебе скачать его.")

@dp.message_handler(content_types=types.ContentType.TEXT)
async def process_video_link(message: types.Message):
    url = message.text.strip()

    ydl_opts = {"quiet": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get("formats", [])

        keyboard = InlineKeyboardMarkup(row_width=2)
        quality_options = {}

        for f in formats:
            if f.get("vcodec") != "none" and f.get("acodec") != "none":  # Только видео с аудио
                res = f.get("format_note", "Unknown")
                file_size = f.get("filesize", 0) or f.get("filesize_approx", 0)  # Получаем размер файла

                if file_size > 2 * 1024 * 1024 * 1024:  # Больше 2ГБ?
                    continue  # Пропускаем этот вариант

                quality_options[res] = f["format_id"]

        for res, format_id in quality_options.items():
            keyboard.insert(InlineKeyboardButton(text=res, callback_data=f"download|{url}|{format_id}"))

        # Кнопка для скачивания только аудио
        keyboard.insert(InlineKeyboardButton(text="🎵 Скачать аудио (MP3)", callback_data=f"download_audio|{url}"))

        if quality_options:
            await message.answer("Выберите качество видео:", reply_markup=keyboard)
        else:
            await message.answer("Видео слишком большое (>2ГБ) или недоступно для скачивания.")

    except Exception as e:
        await message.answer("Ошибка обработки видео. Возможно, оно приватное или недоступно.")
        logging.error(f"Ошибка: {e}")

@dp.callback_query(lambda c: c.data.startswith("download") or c.data.startswith("download_audio"))
async def download_video(callback_query: types.CallbackQuery):
    data = callback_query.data.split("|")
    is_audio = data[0] == "download_audio"
    url = data[1]
    format_id = data[2] if not is_audio else "bestaudio"

    user_id = callback_query.from_user.id
    filename = f"{user_id}.{'mp4' if not is_audio else 'mp3'}"

    ydl_opts = {
        "outtmpl": filename,
        "quiet": True,
        "format": format_id,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}] if is_audio else [],
    }

    progress_msg = await bot.send_message(user_id, "⏳ Скачивание видео...")

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([url]))

        await progress_msg.edit_text("✅ Отправка видео...")

        with open(filename, "rb") as file:
            if is_audio:
                await bot.send_audio(user_id, file, title="Аудио из YouTube")
            else:
                await bot.send_video(user_id, file)

        await progress_msg.delete()

        # Удаляем файл через 10 минут
        asyncio.create_task(delete_file_after_delay(filename, delay=600))

    except Exception as e:
        await progress_msg.edit_text("❌ Ошибка при скачивании видео.")
        logging.error(f"Ошибка загрузки видео: {e}")

async def delete_file_after_delay(file_path, delay=600):
    """Удаляет файл через заданное время (по умолчанию 10 минут)."""
    await asyncio.sleep(delay)
    if os.path.exists(file_path):
        os.remove(file_path)

async def main():
    """Запуск бота"""
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
