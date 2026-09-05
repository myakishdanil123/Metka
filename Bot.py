import re
import html
import math
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
# Visicom
VISICOM_API_KEY = "e14865d659080719d865805b00e967e6"
# Mapbox
# Если пока нет ключа — оставь пустым ""
MAPBOX_TOKEN = "pk.eyJ1IjoibXlha2lzaDEiLCJhIjoiY210bnFscjVtMGd0NzJ3cjM5Y3Z6anJrciJ9.nHWBCkwZk2fLsHp1cFsjpg"
CITY_RU = "Кривой Рог"
CITY_UA = "Кривий Ріг"
# Координаты Кривого Рога.
# Используются как дополнительная защита от результатов
# из другого города.
CITY_LAT = 47.91
CITY_LON = 33.39
# Максимальное расстояние от центра Кривого Рога,
# после которого результат считается подозрительным.
MAX_CITY_DISTANCE_KM = 45
# ============================================================
# VISICOM
# ============================================================
VISICOM_URL = (
    "https://api.visicom.ua/data-api/5.0/uk/geocode.json"
)
# ============================================================
# MAPBOX
# ============================================================
MAPBOX_URL = (
    "https://api.mapbox.com/search/geocode/v6/forward"
)
# ============================================================
# OSM
# ============================================================
OSM_URL = (
    "https://nominatim.openstreetmap.org/search"
)
# ============================================================
# НОРМАЛИЗАЦИЯ
# ============================================================
def normalize(text):
    text = text.lower().strip()
    text = text.replace("ё", "е")
    text = text.replace("ґ", "г")
    replacements = [
        "улица ",
        "ул. ",
        "ул ",
        "вулиця ",
        "вул. ",
        "вул ",
        "проспект ",
        "просп. ",
        "просп ",
        "переулок ",
        "пер. ",
        "пер ",
        "провулок ",
        "пров. ",
        "пров ",
        "бульвар ",
        "бул. ",
        "бул ",
        "площадь ",
        "пл. ",
        "пл ",
        "шоссе ",
        "ш. ",
        "ш "
    ]
    for item in replacements:
        text = text.replace(item, "")
    text = re.sub(r"[.,;:]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
# ============================================================
# ИЗВЛЕЧЕНИЕ НОМЕРА ДОМА
# ============================================================
def extract_house(text):
    text = text.lower()
    patterns = [
        r"\b(\d+\s*[а-яa-zіїєґ]?(?:[-/]\s*\d+\s*[а-яa-zіїєґ]?)?)\b"
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return re.sub(
                r"\s+",
                "",
                match.group(1)
            )
    return None
# ============================================================
# РАЗБОР АДРЕСА
# ============================================================
def parse_address(text):
    text = text.strip()
    house = extract_house(text)
    if not house:
        return None
    # Удаляем номер дома
    street = re.sub(
        r"\b" + re.escape(house) + r"\b",
        "",
        text,
        flags=re.IGNORECASE
    )
    street = normalize(street)
    if len(street) < 2:
        return None
    # Не принимаем обычные предложения
    bad_words = [
        "привет",
        "здравствуйте",
        "спасибо",
        "пожалуйста",
        "машина",
        "машину",
        "машины",
        "кто",
        "что",
        "почему",
        "зачем",
        "можно",
        "нужно",
        "сейчас",
        "там",
        "здесь",
        "ребята"
    ]
    if any(
        word in street.split()
        for word in bad_words
    ):
        return None
    return {
        "street": street,
        "house": house
    }
# ============================================================
# РАССТОЯНИЕ МЕЖДУ КООРДИНАТАМИ
# ============================================================
def distance_m(lat1, lon1, lat2, lon2):
    R = 6371000
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
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
# ПРОВЕРКА, ЧТО КООРДИНАТЫ РЯДОМ С КРИВЫМ РОГОМ
# ============================================================
def is_inside_kryvyi_rih(lat, lon):
    distance = distance_m(
        CITY_LAT,
        CITY_LON,
        lat,
        lon
    )
    return distance <= MAX_CITY_DISTANCE_KM * 1000
# ============================================================
# VISICOM
# ============================================================
def search_visicom(street, house):
    params = {
        "categories": "adr_address",
        "text": f"{CITY_UA}, {street}, {house}",
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
        results = []
        for feature in data.get(
            "features",
            []
        ):
            properties = feature.get(
                "properties",
                {}
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
                coordinates = centroid.get(
                    "coordinates"
                )
                if (
                    not coordinates
                    or len(coordinates) < 2
                ):
                    continue
                lon = float(
                    coordinates[0]
                )
                lat = float(
                    coordinates[1]
                )
            else:
                continue
            if not is_inside_kryvyi_rih(
                lat,
                lon
            ):
                continue
            label = (
                properties.get("label")
                or properties.get("name")
                or ""
            )
            results.append({
                "source": "Visicom",
                "lat": lat,
                "lon": lon,
                "label": label,
                "quality": 3
            })
        return results
    except Exception as e:
        print(
            "VISICOM ERROR:",
            e
        )
        return []
# ============================================================
# MAPBOX
# ============================================================
def search_mapbox(street, house):
    if not MAPBOX_TOKEN:
        return []
    params = {
        "address_number": house,
        "street": street,
        "place": CITY_RU,
        "country": "UA",
        "types": "address",
        "autocomplete": "false",
        "limit": 5,
        "access_token": MAPBOX_TOKEN
    }
    try:
        response = requests.get(
            MAPBOX_URL,
            params=params,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        results = []
        for feature in data.get(
            "features",
            []
        ):
            coordinates = (
                feature
                .get("geometry", {})
                .get("coordinates")
            )
            if (
                not coordinates
                or len(coordinates) < 2
            ):
                continue
            lon = float(
                coordinates[0]
            )
            lat = float(
                coordinates[1]
            )
            if not is_inside_kryvyi_rih(
                lat,
                lon
            ):
                continue
            properties = feature.get(
                "properties",
                {}
            )
            accuracy = properties.get(
                "accuracy",
                ""
            )
            match_code = properties.get(
                "match_code",
                {}
            )
            confidence = (
                match_code.get(
                    "confidence",
                    ""
                )
            )
            # Оценка качества
            quality = 3
            if accuracy == "rooftop":
                quality = 6
            elif accuracy == "parcel":
                quality = 5
            elif accuracy == "point":
                quality = 4
            elif accuracy == "interpolated":
                quality = 2
            elif accuracy == "approximate":
                quality = 0
            if confidence == "exact":
                quality += 2
            elif confidence == "high":
                quality += 1
            results.append({
                "source": "Mapbox",
                "lat": lat,
                "lon": lon,
                "label": feature.get(
                    "properties",
                    {}
                ).get(
                    "name",
                    ""
                ),
                "quality": quality,
                "accuracy": accuracy,
                "confidence": confidence
            })
        return results
    except Exception as e:
        print(
            "MAPBOX ERROR:",
            e
        )
        return []
# ============================================================
# OPENSTREETMAP
# ============================================================
def search_osm(street, house):
    headers = {
        "User-Agent":
            "KryvyiRihTelegramAddressBot/2.0"
    }
    params = {
        "street": f"{street}, {house}",
        "city": CITY_RU,
        "country": "Украина",
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 5
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
        results = []
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
            if not is_inside_kryvyi_rih(
                lat,
                lon
            ):
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
            # Если город явно указан,
            # проверяем его
            if city:
                if (
                    "крив" not in city
                    and "kryv" not in city
                ):
                    continue
            display_name = item.get(
                "display_name",
                ""
            )
            quality = 3
            # Если OSM явно считает это адресом
            if (
                item.get("type")
                == "house"
            ):
                quality = 5
            results.append({
                "source": "OpenStreetMap",
                "lat": lat,
                "lon": lon,
                "label": display_name,
                "quality": quality
            })
        return results
    except Exception as e:
        print(
            "OSM ERROR:",
            e
        )
        return []
# ============================================================
# ПОИСК КЛАСТЕРОВ
# ============================================================
def make_clusters(results):
    clusters = []
    for result in results:
        added = False
        for cluster in clusters:
            center = cluster[0]
            distance = distance_m(
                result["lat"],
                result["lon"],
                center["lat"],
                center["lon"]
            )
            # 120 метров.
            # Результаты в пределах этого расстояния
            # считаем одним местом.
            if distance <= 120:
                cluster.append(
                    result
                )
                added = True
                break
        if not added:
            clusters.append(
                [result]
            )
    return clusters
# ============================================================
# ВЫБОР ЛУЧШЕГО КЛАСТЕРА
# ============================================================
def choose_best(results):
    if not results:
        return None
    clusters = make_clusters(
        results
    )
    best_cluster = None
    best_score = -1
    for cluster in clusters:
        sources = set(
            item["source"]
            for item in cluster
        )
        # Количество независимых источников
        source_count = len(
            sources
        )
        quality_sum = sum(
            item.get(
                "quality",
                0
            )
            for item in cluster
        )
        # Чем больше источников подтверждают
        # одну точку — тем лучше.
        score = (
            source_count * 10
            + quality_sum
        )
        # Дополнительный бонус,
        # если несколько источников
        # реально сошлись.
        if source_count >= 2:
            score += 10
        if source_count >= 3:
            score += 15
        if score > best_score:
            best_score = score
            best_cluster = cluster
    if not best_cluster:
        return None
    # Если есть только один результат
    # низкого качества — НЕ доверяем ему.
    if (
        len(best_cluster) == 1
        and best_cluster[0].get(
            "quality",
            0
        ) < 4
    ):
        return None
    # ========================================================
    # ВЫБИРАЕМ ЛУЧШУЮ ТОЧКУ ВНУТРИ КЛАСТЕРА
    # ========================================================
    best = max(
        best_cluster,
        key=lambda x: x.get(
            "quality",
            0
        )
    )
    return {
        "lat": best["lat"],
        "lon": best["lon"],
        "label": best.get(
            "label",
            ""
        ),
        "sources": sorted(
            set(
                x["source"]
                for x in best_cluster
            )
        ),
        "score": best_score,
        "count": len(best_cluster)
    }
# ============================================================
# ПОЛНЫЙ ПОИСК
# ============================================================
def find_best_address(
    street,
    house
):
    all_results = []
    # Visicom
    visicom = search_visicom(
        street,
        house
    )
    all_results.extend(
        visicom
    )
    # Mapbox
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
        "================================"
    )
    print(
        "SEARCH:",
        street,
        house
    )
    for result in all_results:
        print(
            result["source"],
            result["lat"],
            result["lon"],
            result.get(
                "quality",
                0
            )
        )
    print(
        "================================"
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
    text = text.strip()
    address = parse_address(
        text
    )
    # Обычные сообщения игнорируем
    if not address:
        return
    street = address["street"]
    house = address["house"]
    result = find_best_address(
        street,
        house
    )
    # ========================================================
    # НЕТ ДОСТАТОЧНОГО ПОДТВЕРЖДЕНИЯ
    # ========================================================
    if not result:
        await update.message.reply_text(
            "⚠️ Не удалось достаточно точно "
            "подтвердить этот дом.\n\n"
            "Метка НЕ отправлена, чтобы "
            "не показать неправильное место."
        )
        return
    lat = result["lat"]
    lon = result["lon"]
    sources = ", ".join(
        result["sources"]
    )
    google_maps = (
        "https://www.google.com/maps/search/"
        "?api=1"
        f"&query={lat:.7f},{lon:.7f}"
    )
    message = (
        "📍 <b>Адрес подтверждён</b>\n\n"
        f"<b>{html.escape(street)}, "
        f"{html.escape(house)}</b>\n\n"
        f"Координаты:\n"
        f"<code>{lat:.7f}, "
        f"{lon:.7f}</code>\n\n"
        f"✅ Проверено: "
        f"{html.escape(sources)}\n\n"
        f"🗺 <a href=\"{google_maps}\">"
        f"Открыть в Google Maps"
        f"</a>"
    )
    await update.message.reply_text(
        message,
        parse_mode="HTML"
    )
# ============================================================
# ЗАПУСК
# ============================================================
def main():
    if (
        not TELEGRAM_TOKEN
        or TELEGRAM_TOKEN
        == "ВСТАВЬ_ТОКЕН_TELEGRAM"
    ):
        print(
            "❌ Не указан Telegram token"
        )
        return
    if (
        not VISICOM_API_KEY
        or VISICOM_API_KEY
        == "ВСТАВЬ_VISICOM_API_KEY"
    ):
        print(
            "❌ Не указан Visicom API key"
        )
        return
    print(
        "===================================="
    )
    print(
        "KRYVYI RIH ADDRESS BOT"
    )
    print(
        "VISICOM + MAPBOX + OSM"
    )
    print(
        "STRICT ADDRESS VERIFICATION"
    )
    print(
        "===================================="
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
