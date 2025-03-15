import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes
from telegram.ext import filters
import yt_dlp
from hurry.filesize import size

TOKEN = '7787818513:AAEZwJ-6tl1B7NN_GdgL0P1GqXWiqVKLEBU'  # Замените на токен вашего бота
COOKIES_FILE = 'youtube_cookies.txt'  # Путь к файлу с cookies

# Базовые настройки yt-dlp
ydl_opts_base = {
    'merge_output_format': 'mp4',
    'outtmpl': 'downloads/%(title)s.%(ext)s',
    'cookiefile': COOKIES_FILE,
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        'Привет! Отправь мне ссылку на YouTube видео (будет выбрано качество 1080p или выше).'
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = update.message.text

    if 'youtube.com' not in url and 'youtu.be' not in url:
        await update.message.reply_text('Пожалуйста, отправь ссылку на YouTube видео.')
        return

    try:
        # Получаем информацию о видео
        with yt_dlp.YoutubeDL({
            'quiet': True,
            'cookiefile': COOKIES_FILE,
            'listformats': True  # Включаем вывод всех форматов для отладки
        }) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=False)

        title = info.get('title', 'N/A')
        duration = info.get('duration', 0)
        duration_str = f"{duration // 60:02d}:{duration % 60:02d}"
        views = info.get('view_count', 'N/A')
        uploader = info.get('uploader', 'N/A')

        formats = info.get('formats', [])
        quality_options = []
        has_ready_1080p = False

        # Отладочная информация: выводим все доступные форматы
        print("Доступные форматы:")
        for f in formats:
            print(f"Format ID: {f.get('format_id')}, Height: {f.get('height')}, Resolution: {f.get('resolution')}, "
                  f"vcodec: {f.get('vcodec')}, acodec: {f.get('acodec')}, fps: {f.get('fps')}")

        # Ищем готовые форматы с разрешением 1080p или выше (видео + аудио)
        for f in formats:
            height = f.get('height')
            vcodec = f.get('vcodec')
            acodec = f.get('acodec')
            if height and height >= 1080 and vcodec and vcodec != 'none' and acodec and acodec != 'none':
                resolution = f.get('resolution', 'unknown')
                fps = f.get('fps', 'N/A')
                filesize = f.get('filesize', 0) or f.get('filesize_approx', 0)
                format_id = f.get('format_id')
                quality_options.append({
                    'text': f"{resolution} {fps}fps (Готовое, {size(filesize) if filesize else 'N/A'})",
                    'format_id': format_id,
                    'filesize': filesize
                })
                has_ready_1080p = True

        # Если нет готовых форматов, ищем лучшие видео для объединения с аудио
        if not has_ready_1080p:
            for f in formats:
                height = f.get('height')
                vcodec = f.get('vcodec')
                if height and height >= 1080 and vcodec and vcodec != 'none':
                    resolution = f.get('resolution', 'unknown')
                    fps = f.get('fps', 'N/A')
                    filesize = f.get('filesize', 0) or f.get('filesize_approx', 0)
                    format_id = f.get('format_id')
                    quality_options.append({
                        'text': f"{resolution} {fps}fps (Объединенное, {size(filesize) if filesize else 'N/A'})",
                        'format_id': format_id,
                        'filesize': filesize,
                        'is_combined': True
                    })

        if not quality_options:
            await update.message.reply_text(
                "Видео в разрешении 1080p или выше с аудио недоступно. Попробуйте другое видео."
            )
            return

        # Ограничиваем callback_data
        keyboard = [
            [InlineKeyboardButton(q['text'], callback_data=f"{format_id}|{url}|{q.get('is_combined', False)}")]
            for q in quality_options[-5:]  # Показываем до 5 вариантов
        ]

        video_info = (
            f"Название: {title}\n"
            f"Длительность: {duration_str}\n"
            f"Просмотров: {views:,}\n"
            f"Автор: {uploader}\n\n"
            "Выберите качество (1080p или выше):"
        )

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(video_info, reply_markup=reply_markup)

    except Exception as e:
        await update.message.reply_text(f'Ошибка: {str(e)}')


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    format_id, url, is_combined = query.data.split('|')
    is_combined = bool(is_combined == 'True')

    await query.edit_message_text("Начинаю скачивание...")

    try:
        ydl_opts = ydl_opts_base.copy()
        if is_combined:
            ydl_opts['format'] = f"{format_id}+bestaudio/best"  # Объединяем видео и аудио
        else:
            ydl_opts['format'] = format_id  # Используем готовый формат

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=True)
            filename = ydl.prepare_filename(info)

        actual_size = os.path.getsize(filename)
        if actual_size > 50 * 1024 * 1024:  # Telegram ограничивает файлы до 50 МБ
            download_url = info.get('url', url)
            await query.message.reply_text(
                f"Видео слишком большое ({size(actual_size)}). Вот ссылка для скачивания:\n{download_url}"
            )
        else:
            with open(filename, 'rb') as video:
                await query.message.reply_video(
                    video=video,
                    supports_streaming=True
                )

        os.remove(filename)
        await query.message.delete()

    except Exception as e:
        await query.edit_message_text(f'Ошибка: {str(e)}')


def main() -> None:
    if not os.path.exists(COOKIES_FILE):
        print(f"Файл {COOKIES_FILE} не найден. Проверьте его наличие.")
        return

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button))

    if not os.path.exists('downloads'):
        os.makedirs('downloads')

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
