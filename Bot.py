import re
import requests
from urllib.parse import quote
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters
)
# =========================
# НАСТРОЙКИ
# =========================
TELEGRAM_TOKEN = "8055606612:AAGwAykeVxHwUwHCyw-ECgSMcdVuZHY6Vds"
VISICOM_API_KEY = "e14865d659080719d865805b00e967e6"
CITY = "Кривой Рог"
VISICOM_URL = (
    "https://api.visicom.ua/data-api/5.0/ru/geocode.json"
)
# =========================
# ПОИСК АДРЕСА
# =========================
def find_address(address: str):
    params = {
        "text": f"{CITY}, {address}",
        "country": "UA",
        "limit": 5,
        "key": VISICOM_API_KEY
    }
    try:
        response = requests.get(
            VISICOM_URL,
            params=params,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        features = data.get("features", [])
        if not features:
            return None
        # Берём первый наиболее релевантный результат
        result = features[0]
        properties = result.get("properties", {})
        # Visicom обычно отдаёт geo_centroid
        centroid = properties.get("geo_centroid")
        if not centroid:
            centroid = result.get("geo_centroid")
        if not centroid:
            return None
        # Формат может быть [longitude, latitude]
        if isinstance(centroid, list):
            longitude = centroid[0]
            latitude = centroid[1]
        elif isinstance(centroid, dict):
            longitude = centroid.get("coordinates", [None, None])[0]
            latitude = centroid.get("coordinates", [None, None])[1]
        else:
            return None
        if longitude is None or latitude is None:
            return None
        name = (
            properties.get("label")
            or properties.get("name")
            or address
        )
        return {
            "name": name,
            "latitude": latitude,
            "longitude": longitude
        }
    except Exception as e:
        print("Ошибка Visicom:", e)
        return None
# =========================
# ПРОВЕРКА, ПОХОЖЕ ЛИ СООБЩЕНИЕ
# НА АДРЕС
# =========================
def looks_like_address(text: str) -> bool:
    text = text.strip().lower()
    # Слишком короткие сообщения игнорируем
    if len(text) < 3:
        return False
    # Обычные фразы не обрабатываем
    ignored = {
        "привет",
        "здравствуйте",
        "спасибо",
        "доброе утро",
        "добрый день",
        "добрый вечер",
        "ок",
        "да",
        "нет",
        "хорошо",
        "понял",
        "понятно"
    }
    if text in ignored:
        return False
    # Если есть номер дома — почти наверняка адрес
    if re.search(r"\b\d+[а-яa-z]?\b", text):
        return True
    # Ключевые слова адреса
    street_words = [
        "ул",
        "улица",
        "вул",
        "вулиця",
        "проспект",
        "просп",
        "пр",
        "площадь",
        "пл",
        "площа",
        "шоссе",
        "ш",
        "переулок",
        "пер",
        "провулок",
        "бульвар",
        "бул",
        "набережная",
        "наб",
        "дорога"
    ]
    for word in street_words:
        if re.search(rf"\b{re.escape(word)}\b", text):
            return True
    # Если сообщение состоит из нескольких слов,
    # пробуем поиск как название улицы
    words = text.split()
    if 1 <= len(words) <= 5 and all(
        re.match(r"^[а-яёіїєґa-z0-9'’\-]+$", w)
        for w in words
    ):
        return True
    return False
# =========================
# ОБРАБОТКА СООБЩЕНИЙ
# =========================
async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return
    text = update.message.text
    if not text:
        return
    text = text.strip()
    # Не реагируем на обычные сообщения
    if not looks_like_address(text):
        return
    print("Ищем:", text)
    result = find_address(text)
    if not result:
        await update.message.reply_text(
            "❌ Адрес не найден."
        )
        return
    latitude = result["latitude"]
    longitude = result["longitude"]
    name = result["name"]
    # Google Maps
    google_maps = (
        f"https://www.google.com/maps/search/?api=1"
        f"&query={latitude},{longitude}"
    )
    message = (
        f"📍 <b>{name}</b>\n\n"
        f"Координаты:\n"
        f"<code>{latitude}, {longitude}</code>\n\n"
        f"🌎 <a href=\"{google_maps}\">Открыть в Google Maps</a>"
    )
    await update.message.reply_text(
        message,
        parse_mode="HTML",
        disable_web_page_preview=False
    )
# =========================
# ЗАПУСК БОТА
# =========================
def main():
    if TELEGRAM_TOKEN == "ВСТАВЬ_СЮДА_ТОКЕН_БОТА":
        print("❌ Не указан Telegram TOKEN")
        return
    if VISICOM_API_KEY == "ВСТАВЬ_СЮДА_VISICOM_API_KEY":
        print("❌ Не указан Visicom API KEY")
        return
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )
    print("✅ Бот запущен")
    print("📍 Поиск адресов: Кривой Рог")
    print("🗺️ Visicom → Google Maps")
    app.run_polling()
if __name__ == "__main__":
    main()
