import re
import html
import math
import time
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
# Можно оставить пустым.
# Если есть Mapbox token — поиск станет лучше.
MAPBOX_TOKEN = "pk.eyJ1IjoibXlha2lzaDEiLCJhIjoiY210bnFscjVtMGd0NzJ3cjM5Y3Z6anJrciJ9.nHWBCkwZk2fLsHp1cFsjpg"
CITY_RU = "Кривой Рог"
CITY_UA = "Кривий Ріг"
COUNTRY = "Украина"
# Центр Кривого Рога
CITY_LAT = 47.9105
CITY_LON = 33.3918
# Не принимать результаты совсем далеко от города
MAX_CITY_DISTANCE_KM = 60
# ============================================================
# API
# ============================================================
VISICOM_URL = (
    "https://api.visicom.ua/data-api/5.0/uk/geocode.json"
)
MAPBOX_URL = (
    "https://api.mapbox.com/search/geocode/v6/forward"
)
OSM_URL = (
    "https://nominatim.openstreetmap.org/search"
)
# ============================================================
# СИНОНИМЫ ТИПОВ УЛИЦ
# ============================================================
STREET_WORDS = [
    "улица",
    "ул",
    "вулиця",
    "вул",
    "проспект",
    "просп",
    "переулок",
    "пер",
    "провулок",
    "пров",
    "бульвар",
    "бул",
    "площадь",
    "пл",
    "площа",
    "шоссе",
    "ш",
    "набережная",
    "наб"
]
# ============================================================
# НОРМАЛИЗАЦИЯ
# ============================================================
def normalize(text):
    text = text.lower().strip()
    text = text.replace("ё", "е")
    text = text.replace("ґ", "г")
    text = text.replace("’", "'")
    text = text.replace("`", "'")
    # Убираем тип улицы
    for word in STREET_WORDS:
        text = re.sub(
            rf"\b{re.escape(word)}\.?\b",
            " ",
            text
        )
    text = re.sub(
        r"[.,;:]+",
        " ",
        text
    )
    text = re.sub(
        r"\s+",
        " ",
        text
    )
    return text.strip()
# ============================================================
# НОРМАЛИЗАЦИЯ НОМЕРА ДОМА
# ============================================================
def normalize_house(house):
    if not house:
        return ""
    house = house.lower()
    house = house.replace(
        " ",
        ""
    )
    house = house.replace(
        "а",
        "а"
    )
    return house
# ============================================================
# НОМЕР ДОМА
# ============================================================
def extract_house(text):
    # Поддерживает:
    #
    # 12
    # 12а
    # 12-А
    # 12/1
    # 12-а/1
    patterns = [
        r"\b\d+\s*[а-яa-zіїєґ]?\s*"
        r"(?:[/\-]\s*\d+\s*[а-яa-zіїєґ]?)?\b"
    ]
    for pattern in patterns:
        match = re.search(
            pattern,
            text.lower()
        )
        if match:
            return normalize_house(
                match.group(0)
            )
    return None
# ============================================================
# РАЗБОР АДРЕСА
# ============================================================
def parse_address(text):
    text = text.strip()
    if len(text) < 3:
        return None
    house = extract_house(text)
    if not house:
        return None
    # Убираем номер дома
    street = re.sub(
        r"\b" + re.escape(house) + r"\b",
        " ",
        text,
        flags=re.IGNORECASE
    )
    street = normalize(
        street
    )
    if len(street) < 2:
        return None
    return {
        "street": street,
        "house": house
    }
# ============================================================
# РАЗНЫЕ ВАРИАНТЫ АДРЕСА
# ============================================================
def address_variants(
    street,
    house
):
    variants = []
    variants.append(
        f"{CITY_UA}, {street}, {house}"
    )
    variants.append(
        f"{CITY_RU}, {street}, {house}"
    )
    variants.append(
        f"{street}, {house}, {CITY_UA}"
    )
    variants.append(
        f"{street} {house}, {CITY_RU}"
    )
    variants.append(
        f"{street} {house}"
    )
    # Убираем дубли
    unique = []
    for item in variants:
        if item not in unique:
            unique.append(item)
    return unique
# ============================================================
# РАССТОЯНИЕ
# ============================================================
def distance_m(
    lat1,
    lon1,
    lat2,
    lon2
):
    R = 6371000
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(
        lat2 - lat1
    )
    dl = math.radians(
        lon2 - lon1
    )
    a = (
        math.sin(dp / 2) ** 2
        +
        math.cos(p1)
        * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )
    return (
        R
        * 2
        * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )
    )
# ============================================================
# ПРОВЕРКА ГОРОДА
# ============================================================
def city_distance(
    lat,
    lon
):
    return distance_m(
        CITY_LAT,
        CITY_LON,
        lat,
        lon
    )
def is_reasonable_location(
    lat,
    lon
):
    return (
        city_distance(
            lat,
            lon
        )
        <= MAX_CITY_DISTANCE_KM * 1000
    )
# ============================================================
# ПРОВЕРКА НАЗВАНИЯ
# ============================================================
def text_contains_street(
    result_text,
    street
):
    if not result_text:
        return False
    a = normalize(
        result_text
    )
    b = normalize(
        street
    )
    if not b:
        return False
    # Полное совпадение
    if b in a:
        return True
    # Слова улицы
    street_words = b.split()
    if len(street_words) == 1:
        return street_words[0] in a
    # Все слова должны присутствовать
    return all(
        word in a
        for word in street_words
    )
# ============================================================
# ПРОВЕРКА НОМЕРА
# ============================================================
def text_contains_house(
    result_text,
    house
):
    if not result_text:
        return False
    result_text = result_text.lower()
    house = normalize_house(
        house
    )
    # Ищем именно номер как отдельную часть
    pattern = (
        r"(?<!\d)"
        + re.escape(house)
        + r"(?!\d)"
    )
    return bool(
        re.search(
            pattern,
            result_text
        )
    )
# ============================================================
# VISICOM
# ============================================================
def search_visicom(
    street,
    house
):
    results = []
    variants = address_variants(
        street,
        house
    )
    for query in variants:
        params = {
            "categories": "adr_address",
            "text": query,
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
            for feature in data.get(
                "features",
                []
            ):
                properties = (
                    feature.get(
                        "properties",
                        {}
                    )
                )
                centroid = (
                    properties.get(
                        "geo_centroid"
                    )
                    or feature.get(
                        "geo_centroid"
                    )
                )
                if not centroid:
                    continue
                if isinstance(
                    centroid,
                    list
                ):
                    if len(centroid) < 2:
                        continue
                    lon = float(
                        centroid[0]
                    )
                    lat = float(
                        centroid[1]
                    )
                elif isinstance(
                    centroid,
                    dict
                ):
                    coords = (
                        centroid.get(
                            "coordinates"
                        )
                    )
                    if (
                        not coords
                        or len(coords) < 2
                    ):
                        continue
                    lon = float(
                        coords[0]
                    )
                    lat = float(
                        coords[1]
                    )
                else:
                    continue
                if not is_reasonable_location(
                    lat,
                    lon
                ):
                    continue
                label = (
                    properties.get(
                        "label"
                    )
                    or properties.get(
                        "name"
                    )
                    or ""
                )
                score = 5
                if text_contains_street(
                    label,
                    street
                ):
                    score += 5
                if text_contains_house(
                    label,
                    house
                ):
                    score += 8
                results.append({
                    "source": "Visicom",
                    "lat": lat,
                    "lon": lon,
                    "label": label,
                    "score": score
                })
        except Exception as e:
            print(
                "VISICOM:",
                e
            )
    return results
# ============================================================
# MAPBOX
# ============================================================
def search_mapbox(
    street,
    house
):
    if not MAPBOX_TOKEN:
        return []
    results = []
    queries = address_variants(
        street,
        house
    )
    for query in queries:
        params = {
            "q": query,
            "country": "UA",
            "types": "address",
            "limit": 10,
            "access_token":
                MAPBOX_TOKEN
        }
        try:
            response = requests.get(
                MAPBOX_URL,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            for feature in data.get(
                "features",
                []
            ):
                coords = (
                    feature
                    .get(
                        "geometry",
                        {}
                    )
                    .get(
                        "coordinates"
                    )
                )
                if (
                    not coords
                    or len(coords) < 2
                ):
                    continue
                lon = float(
                    coords[0]
                )
                lat = float(
                    coords[1]
                )
                if not is_reasonable_location(
                    lat,
                    lon
                ):
                    continue
                properties = (
                    feature.get(
                        "properties",
                        {}
                    )
                )
                full_text = (
                    properties.get(
                        "full_address"
                    )
                    or feature.get(
                        "place_name"
                    )
                    or ""
                )
                accuracy = (
                    properties.get(
                        "coordinates",
                        {}
                    ).get(
                        "accuracy",
                        ""
                    )
                )
                score = 5
                if accuracy == "rooftop":
                    score += 12
                elif accuracy == "parcel":
                    score += 10
                elif accuracy == "point":
                    score += 8
                elif accuracy == "interpolated":
                    score += 3
                elif accuracy == "approximate":
                    score -= 5
                if text_contains_street(
                    full_text,
                    street
                ):
                    score += 5
                if text_contains_house(
                    full_text,
                    house
                ):
                    score += 8
                results.append({
                    "source": "Mapbox",
                    "lat": lat,
                    "lon": lon,
                    "label": full_text,
                    "accuracy": accuracy,
                    "score": score
                })
        except Exception as e:
            print(
                "MAPBOX:",
                e
            )
    return results
# ============================================================
# OSM
# ============================================================
def search_osm(
    street,
    house
):
    results = []
    headers = {
        "User-Agent":
            "KryvyiRihAddressBot/3.0"
    }
    queries = [
        f"{street} {house}, "
        f"{CITY_UA}, Ukraine",
        f"{street} {house}, "
        f"{CITY_RU}, Ukraine"
    ]
    for query in queries:
        params = {
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": 10
        }
        try:
            response = requests.get(
                OSM_URL,
                params=params,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            for item in data:
                try:
                    lat = float(
                        item["lat"]
                    )
                    lon = float(
                        item["lon"]
                    )
                except:
                    continue
                if not is_reasonable_location(
                    lat,
                    lon
                ):
                    continue
                address = item.get(
                    "address",
                    {}
                )
                full_text = item.get(
                    "display_name",
                    ""
                )
                score = 4
                # Реальный объект дома
                if item.get(
                    "type"
                ) == "house":
                    score += 10
                if text_contains_street(
                    full_text,
                    street
                ):
                    score += 5
                if text_contains_house(
                    full_text,
                    house
                ):
                    score += 8
                results.append({
                    "source":
                        "OpenStreetMap",
                    "lat": lat,
                    "lon": lon,
                    "label": full_text,
                    "score": score
                })
            # Nominatim требует
            # не делать частые запросы
            time.sleep(1)
        except Exception as e:
            print(
                "OSM:",
                e
            )
    return results
# ============================================================
# УДАЛЕНИЕ ДУБЛЕЙ
# ============================================================
def remove_duplicates(
    results
):
    unique = []
    for result in results:
        duplicate = False
        for old in unique:
            d = distance_m(
                result["lat"],
                result["lon"],
                old["lat"],
                old["lon"]
            )
            if d < 10:
                # Оставляем лучший результат
                if (
                    result["score"]
                    >
                    old["score"]
                ):
                    unique.remove(
                        old
                    )
                    unique.append(
                        result
                    )
                duplicate = True
                break
        if not duplicate:
            unique.append(
                result
            )
    return unique
# ============================================================
# ПОИСК ПОДТВЕРЖДЕНИЙ
# ============================================================
def calculate_confirmation(
    candidate,
    results
):
    confirmation = 0
    sources = set()
    for result in results:
        d = distance_m(
            candidate["lat"],
            candidate["lon"],
            result["lat"],
            result["lon"]
        )
        if d <= 30:
            sources.add(
                result["source"]
            )
            confirmation += 10
        elif d <= 100:
            sources.add(
                result["source"]
            )
            confirmation += 6
        elif d <= 250:
            sources.add(
                result["source"]
            )
            confirmation += 3
    # Бонус за разные источники
    confirmation += (
        len(sources) * 8
    )
    return (
        confirmation,
        sources
    )
# ============================================================
# ВЫБОР ЛУЧШЕГО
# ============================================================
def choose_best(
    results
):
    if not results:
        return None
    results = remove_duplicates(
        results
    )
    candidates = []
    for candidate in results:
        confirmation, sources = (
            calculate_confirmation(
                candidate,
                results
            )
        )
        total_score = (
            candidate["score"]
            + confirmation
        )
        candidates.append({
            **candidate,
            "total_score":
                total_score,
            "sources":
                sources
        })
    candidates.sort(
        key=lambda x:
            x["total_score"],
        reverse=True
    )
    best = candidates[0]
    # ========================================================
    # ЗАЩИТА ОТ ЦЕНТРА УЛИЦЫ
    # ========================================================
    # Если результат один и он слабый —
    # не отправляем.
    if (
        len(results) == 1
        and best["score"] < 12
    ):
        return None
    # Если результат найден одним источником,
    # но сам источник считает его точным —
    # разрешаем.
    if (
        len(best["sources"]) == 1
        and best["score"] < 15
    ):
        return None
    return best
# ============================================================
# ПОЛНЫЙ ПОИСК
# ============================================================
def find_address(
    street,
    house
):
    all_results = []
    # VISICOM
    visicom = search_visicom(
        street,
        house
    )
    all_results.extend(
        visicom
    )
    # MAPBOX
    mapbox = search_mapbox(
        street,
        house
    )
    all_results.extend(
        mapbox
    )
    # OSM
    osm = search_osm(
        street,
        house
    )
    all_results.extend(
        osm
    )
    print(
        "--------------------------------"
    )
    print(
        "ADDRESS:",
        street,
        house
    )
    for result in all_results:
        print(
            result["source"],
            result["lat"],
            result["lon"],
            result["score"]
        )
    print(
        "--------------------------------"
    )
    return choose_best(
        all_results
    )
# ============================================================
# TELEGRAM
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
    address = parse_address(
        text
    )
    # Обычные сообщения
    # полностью игнорируем
    if not address:
        return
    street = address[
        "street"
    ]
    house = address[
        "house"
    ]
    result = find_address(
        street,
        house
    )
    if not result:
        await update.message.reply_text(
            "⚠️ Не удалось достаточно "
            "надёжно определить этот дом.\n\n"
            "Метка не отправлена."
        )
        return
    lat = result["lat"]
    lon = result["lon"]
    sources = ", ".join(
        sorted(
            result["sources"]
        )
    )
    google_maps = (
        "https://www.google.com/maps/"
        "search/?api=1"
        f"&query={lat:.7f},{lon:.7f}"
    )
    message = (
        "📍 <b>Дом найден</b>\n\n"
        f"<b>{html.escape(street)}, "
        f"{html.escape(house)}</b>\n\n"
        f"📌 Координаты:\n"
        f"<code>{lat:.7f}, "
        f"{lon:.7f}</code>\n\n"
        f"🔎 Проверено источников: "
        f"{html.escape(sources)}\n\n"
        f"🗺 <a href=\"{google_maps}\">"
        f"Открыть Google Maps"
        f"</a>"
    )
    await update.message.reply_text(
        message,
        parse_mode="HTML"
    )
# ============================================================
# START
# ============================================================
def main():
    if (
        not TELEGRAM_TOKEN
        or TELEGRAM_TOKEN
        == "ВСТАВЬ_ТОКЕН_TELEGRAM"
    ):
        print(
            "❌ Укажи TELEGRAM_TOKEN"
        )
        return
    if (
        not VISICOM_API_KEY
        or VISICOM_API_KEY
        == "ВСТАВЬ_VISICOM_API_KEY"
    ):
        print(
            "❌ Укажи VISICOM_API_KEY"
        )
        return
    print(
        "=================================="
    )
    print(
        "KRYVYI RIH ADDRESS BOT"
    )
    print(
        "VISICOM + MAPBOX + OSM"
    )
    print(
        "MULTI QUERY SEARCH"
    )
    print(
        "=================================="
    )
    app = (
        Application
        .builder()
        .token(
            TELEGRAM_TOKEN
        )
        .build()
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_message
        )
    )
    app.run_polling()
if __name__ == "__main__":
    main()
