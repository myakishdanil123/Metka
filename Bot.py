import logging
from urllib.parse import quote_plus

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = "8055606612:AAGwAykeVxHwUwHCyw-ECgSMcdVuZHY6Vds"

logging.basicConfig(level=logging.INFO)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Напиши название улицы Кривого Рога.\n\n"
        "Например:\n"
        "📍 Гагарина\n"
        "📍 Соборности\n"
        "📍 Ватутина"
    )


async def handle_street(update: Update, context: ContextTypes.DEFAULT_TYPE):
    street = update.message.text.strip()

    if not street:
        return

    # Добавляем город автоматически
    query = f"улица {street}, Кривой Рог, Украина"

    maps_url = (
        "https://www.google.com/maps/search/?api=1&query="
        + quote_plus(query)
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "📍 Открыть Google Maps",
                url=maps_url
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📍 Улица: {street}\n"
        f"🏙 Кривой Рог\n\n"
        f"Нажми кнопку ниже 👇",
        reply_markup=reply_markup
    )


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_street
        )
    )

    print("🤖 Бот запущен!")

    app.run_polling()


if __name__ == "__main__":
    main()
