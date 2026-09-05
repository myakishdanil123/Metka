import re
import html
import requests
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters
)
# ============================================================
# НАСТРОЙКИ
# ============================================================
TELEGRAM_TOKEN = "8055606612:AAGwAykeVxHwUwHCyw-ECgSMcdVuZHY6Vds"
VISICOM_API_KEY = "e14865d659080719d865805b00e967e6"
CITY_RU = "Кривой Рог"
CITY_UA = "Кривий Ріг"
VISICOM_URL = "https://api.visicom.ua/data-api/5.0/uk/geocode.json"
VISICOM_FEATURE_URL = "https://api.visicom.ua/data-api/5.0/uk/feature"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Максимальное расстояние между результатами двух источников.
# Если больше — адрес считаем сомнительным.
MAX_DISTANCE_METERS = 700
# ============================================================
# НОРМАЛИЗАЦИЯ ТЕКСТА
# ============================================================
def normalize(text):
    text = text.lower().strip()
    replacements = {
        "вул.": "",
        "вул ": "",
        "улица ": "",
        "ул.": "",
        "ул ": "",
        "вулиця ": "",
        "проспект ": "",
        "просп.": "",
        "просп ": "",
        "переулок ": "",
        "пер.": "",
        "пер ": "",
        "провулок ": "",
        "пров.": "",
        "бульвар ": "",
        "бул.": "",
        "площадь ": "",
        "пл.": "",
        "площа ": "",
        "шоссе ": "",
        "ш.": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    return text.strip()
# ============================================================
# ИЗВЛЕЧЕНИЕ НОМЕРА ДОМА
# ============================================================
def extract_house_number(text):
    """
    Поддерживает:
    12
    12а
    12/1
    12-а
    12А
    """
    match = re.search(
        r"(?:^|\s|,)(\d+[а-яa-zіїєґ]?(?:[-/]\d+[а-яa-zіїєґ]?)?)"
        r"(?:\s|$|,)",
        text.lower()
    )
    if match:
        return match.group(1)
    return None
# ============================================================
# ПРОВЕРКА: ЭТО ВООБЩЕ АДРЕСА?
# ============================================================
def parse_address(text):
    text = text.strip()
    if len(text) < 3:
        return None
    house = extract_house_number(
        " " + text + " "
    )
    # Если есть номер дома
    if house:
        # Всё до номера считаем названием улицы
        match = re.search(
            r"^(.*?)[,\s]+"
            + re.escape(house)
            + r"\s*$",
            text,
            re.IGNORECASE
        )
        if match:
            street = match.group(1).strip()
        else:
            # запасной вариант
            street = re.sub(
                r"\b" + re.escape(house) + r"\b",
                "",
                text,
                flags=re.IGNORECASE
            ).strip(" ,")
        street = normalize(street)
        if not street:
            return None
        return {
            "street": street,
            "house": house
        }
    # Без номера дома принимаем только короткое
    # название улицы.
    words = text.split()
    if 1 <= len(words) <= 5:
        # Не принимаем предложения
        bad_words = [
            "привет",
            "здравствуйте",
            "спасибо",
            "пожалуйста",
            "машина",
            "машину",
            "кто",
            "что",
            "как",
            "почему",
            "можно",
            "нужно",
            "сейчас",
            "там",
            "здесь"
        ]
        if any(word.lower() in bad_words for word in words):
            return None
        return {
            "street": normalize(text),
            "house": None
        }
    return None
# ============================================================
# ПОЛУЧЕНИЕ КООРДИНАТ ИЗ VISICOM
# ============================================================
def get_coordinates_from_visicom(address):
    params = {
        "categories": "adr_address",
        "text": f"{CITY_UA}, {address}",
        "country": "UA",
        "limit": 10,
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
        results = []
        for feature in features:
            properties = feature.get("properties", {})
            centroid = properties.get("geo_centroid")
            if not centroid:
                centroid = feature.get("geo_centroid")
            if not centroid:
                continue
            if isinstance(centroid, list):
                if len(centroid) < 2:
                    continue
                longitude = centroid[0]
                latitude = centroid[1]
            elif isinstance(centroid, dict):
                coordinates = centroid.get("coordinates")
                if not coordinates or len(coordinates) < 2:
                    continue
                longitude = coordinates[0]
                latitude = coordinates[1]
            else:
                continue
            try:
                longitude = float(longitude)
                latitude = float(latitude)
            except:
                continue
            # Украина / Кривой Рог приблизительно
            if not (
                47.7 < latitude < 48.4
                and 32.9 < longitude < 34.0
            ):
                continue
            label = (
                properties.get("label")
                or properties.get("name")
                or ""
            )
            results.append({
                "latitude": latitude,
                "longitude": longitude,
                "label": label,
                "id": feature.get("id")
            })
        if not results:
            return None
        return results
    except Exception as e:
        print("VISICOM ERROR:", e)
        return None
# ============================================================
# ПОИСК ЧЕРЕЗ NOMINATIM / OPENSTREETMAP
# ============================================================
def get_coordinates_from_osm(address):
    headers = {
        "User-Agent": "KryvyiRihTelegramAddressBot/1.0"
    }
    params = {
        "street": address,
        "city": CITY_RU,
        "country": "Украина",
        "format": "jsonv2",
        "limit": 5,
        "addressdetails": 1
    }
    try:
        response = requests.get(
            NOMINATIM_URL,
            params=params,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        if not data:
            return None
        results = []
        for item in data:
            try:
                latitude = float(item["lat"])
                longitude = float(item["lon"])
            except:
                continue
            address_data = item.get(
                "address",
                {}
            )
            city = (
                address_data.get("city")
                or address_data.get("town")
                or address_data.get("municipality")
                or ""
            ).lower()
            # Не принимаем результаты из другого города
            if city:
                allowed_city_words = [
                    "крив",
                    "kryvyi",
                    "кривой"
                ]
                if not any(
                    word in city
                    for word in allowed_city_words
                ):
                    continue
            results.append({
                "latitude": latitude,
                "longitude": longitude,
                "label": item.get("display_name", "")
            })
        if not results:
            return None
        return results
    except Exception as e:
        print("OSM ERROR:", e)
        return None
# ============================================================
# РАССТОЯНИЕ МЕЖДУ ДВУМЯ КООРДИНАТАМИ
# ============================================================
def distance_meters(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, atan2
    R = 6371000
    p1 = radians(lat1)
    p2 = radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = (
        sin(dp / 2) ** 2
        +
        cos(p1)
        * cos(p2)
        * sin(dl / 2) ** 2
    )
    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a)
    )
    return R * c
# ============================================================
# ВЫБОР ТОЧНОЙ КООРДИНАТЫ
# ============================================================
def choose_best(visicom_results, osm_results):
    if not visicom_results:
        return None
    # Если OSM ничего не нашёл,
    # Visicom используем только если есть один
    # достаточно однозначный результат.
    if not osm_results:
        if len(visicom_results) == 1:
            return visicom_results[0]
        # Несколько вариантов — не рискуем
        return None
    best = None
    best_distance = None
    for v in visicom_results:
        for o in osm_results:
            distance = distance_meters(
                v["latitude"],
                v["longitude"],
                o["latitude"],
                o["longitude"]
            )
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best = {
                    "latitude": v["latitude"],
                    "longitude": v["longitude"],
                    "label": v["label"],
                    "source_distance": distance
                }
    if best is None:
        return None
    # Источники слишком далеко друг от друга
    if best_distance > MAX_DISTANCE_METERS:
        print(
            f"ADDRESS REJECTED: sources differ "
            f"by {round(best_distance)} meters"
        )
        return None
    return best
# ============================================================
# ПОИСК АДРЕСА
# ============================================================
def find_address(address):
    visicom_results = get_coordinates_from_visicom(
        address
    )
    osm_results = get_coordinates_from_osm(
        address
    )
    print("VISICOM:", visicom_results)
    print("OSM:", osm_results)
    result = choose_best(
        visicom_results,
        osm_results
    )
    return result
# ============================================================
# ПРОВЕРКА СООБЩЕНИЯ
# ============================================================
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
    parsed = parse_address(text)
    # Обычное сообщение — полностью игнорируем
    if not parsed:
        return
    street = parsed["street"]
    house = parsed["house"]
    if house:
        search_address = (
            f"{street}, {house}"
        )
    else:
        # Улица без дома.
        # ВАЖНО: для улицы без номера точность ниже,
        # поэтому такую метку НЕ отправляем автоматически.
        await update.message.reply_text(
            "⚠️ Укажи номер дома.\n\n"
            f"Например: {street} 15"
        )
        return
    print(
        f"SEARCH: {CITY_RU}, {search_address}"
    )
    result = find_address(
        search_address
    )
    # ========================================================
    # НЕ УВЕРЕНЫ — НЕ ОТПРАВЛЯЕМ ЛЕВУЮ ТОЧКУ
    # ========================================================
    if not result:
        await update.message.reply_text(
            "❌ Точный адрес не подтверждён.\n"
            "Метка не отправлена, чтобы не показать "
            "неправильное место."
        )
        return
    latitude = result["latitude"]
    longitude = result["longitude"]
    label = result.get(
        "label",
        search_address
    )
    # ========================================================
    # GOOGLE MAPS
    # ========================================================
    google_maps = (
        "https://www.google.com/maps/search/"
        "?api=1"
        f"&query={latitude},{longitude}"
    )
    # ========================================================
    # TELEGRAM
    # ========================================================
    message = (
        "📍 <b>Адрес найден</b>\n\n"
        f"<b>{html.escape(search_address)}</b>\n\n"
        f"Координаты:\n"
        f"<code>{latitude:.7f}, {longitude:.7f}</code>\n\n"
        f"🌎 <a href=\"{google_maps}\">"
        f"Открыть в Google Maps"
        f"</a>"
    )
    await update.message.reply_text(
        message,
        parse_mode="HTML",
        disable_web_page_preview=False
    )
# ============================================================
# ЗАПУСК
# ============================================================
def main():
    if (
        not TELEGRAM_TOKEN
        or TELEGRAM_TOKEN == "ВСТАВЬ_ТОКЕН_БОТА"
    ):
        print(
            "❌ Вставь Telegram token"
        )
        return
    if (
        not VISICOM_API_KEY
        or VISICOM_API_KEY == "ВСТАВЬ_VISICOM_API_KEY"
    ):
        print(
            "❌ Вставь Visicom API key"
        )
        return
    app = (
        Application
        .builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_message
        )
    )
    print(
        "================================"
    )
    print(
        "BOT STARTED"
    )
    print(
        "CITY: Kryvyi Rih"
    )
    print(
        "VISICOM + OPENSTREETMAP"
    )
    print(
        "STRICT ADDRESS VERIFICATION"
    )
    print(
        "================================"
    )
    app.run_polling()
if __name__ == "__main__":
    main()
