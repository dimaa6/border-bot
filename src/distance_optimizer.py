import logging
from datetime import datetime, timezone
from clients import get_supabase, send_telegram_request
from constants import CMD_CANCEL, CMD_START_CROSSING, CHECKPOINT_CLOSED_ICON
from db_helpers import get_checkpoint_telegram_handles, get_closed_checkpoints
from redis_sessions import (
    increment_plan_route_country_analytics,
    increment_plan_route_direction_analytics,
    increment_plan_route_city_analytics,
    increment_plan_route_funnel_analytics,
)

logger = logging.getLogger(__name__)

# Internal lists used by the system (English keys)
UKRAINIAN_CITIES = ["Lviv", "Lutsk", "Kovel", "Stryi", "Brody"]
POLISH_CITIES = ["Krakow", "Warsaw"]
CHECKPOINTS = [
    "Ustyluh", "Krakivets", "Rava Ruska", "Shehyni", 
    "Uhryniv", "Hrushiv", "Nizhankovichi", "Smilnytsia"
]

UKRAINIAN_CITIES_SK = ["Lviv", "Mukachevo", "Uzhhorod"]
SLOVAK_CITIES = ["Kosice"]
CHECKPOINTS_SK = ["Malyi Bereznyi", "Uzhhorod"]

UKRAINIAN_CITIES_HU = ["Mukachevo", "Uzhhorod", "Khust"]
HUNGARIAN_CITIES = ["Budapest"]
CHECKPOINTS_HU = ["Kosyno", "Chop", "Dzvinkove", "Luzhanka", "Vylok", "Velyka Palad"]

UKRAINIAN_CITIES_RO = ["Mukachevo", "Ivano-Frankivsk", "Chernivtsi", "Odesa"]
ROMANIAN_CITIES = ["Bucharest", "Constanta"]
CHECKPOINTS_RO = ["Orlivka", "Dyakivtsi", "Dyakove", "Krasnoilsk", "Porubne", "Solotvyno", "Reni"]

UKRAINIAN_CITIES_MD = ["Vinnytsia", "Uman", "Odesa"]
MOLDOVAN_CITIES = ["Chisinau"]
CHECKPOINTS_MD = ["Mohyliv-Podilskyi", "Bronnytsya", "Rososhany", "Mamalyha", "Sokyryany", "Mayaky-Udobne", "Dolynske", "Starokozache", "Kelmentsi", "Tabaky"]

COUNTRY_CONFIG = {
    "PL": {
        "name": "Польща",
        "ua_cities": UKRAINIAN_CITIES,
        "foreign_cities": POLISH_CITIES,
        "checkpoints": CHECKPOINTS,
    },
    "SK": {
        "name": "Словаччина",
        "ua_cities": UKRAINIAN_CITIES_SK,
        "foreign_cities": SLOVAK_CITIES,
        "checkpoints": CHECKPOINTS_SK,
    },
    "HU": {
        "name": "Угорщина",
        "ua_cities": UKRAINIAN_CITIES_HU,
        "foreign_cities": HUNGARIAN_CITIES,
        "checkpoints": CHECKPOINTS_HU,
    },
    "RO": {
        "name": "Румунія",
        "ua_cities": UKRAINIAN_CITIES_RO,
        "foreign_cities": ROMANIAN_CITIES,
        "checkpoints": CHECKPOINTS_RO,
    },
    "MD": {
        "name": "Молдова",
        "ua_cities": UKRAINIAN_CITIES_MD,
        "foreign_cities": MOLDOVAN_CITIES,
        "checkpoints": CHECKPOINTS_MD,
    },
}

# Translation mappings: English -> Ukrainian
CITY_EN_TO_UA = {
    "Lviv": "Львів",
    "Lutsk": "Луцьк",
    "Kovel": "Ковель",
    "Stryi": "Стрий",
    "Brody": "Броди",
    "Mukachevo": "Мукачево",
    "Uzhhorod": "Ужгород",
    "Khust": "Хуст",
    "Ivano-Frankivsk": "Івано-Франківськ",
    "Chernivtsi": "Чернівці",
    "Odesa": "Одеса",
    "Vinnytsia": "Вінниця",
    "Uman": "Умань",
    "Krakow": "Краків",
    "Warsaw": "Варшава",
    "Kosice": "Кошице",
    "Budapest": "Будапешт",
    "Bucharest": "Бухарест",
    "Constanta": "Констанца",
    "Chisinau": "Кишинів",
}

# Reverse mapping for when you receive the button click/text from the user: Ukrainian -> English
CITY_UA_TO_EN = {ua: en for en, ua in CITY_EN_TO_UA.items()}

# Translations for checkpoints
CHECKPOINT_EN_TO_UA = {
    "Ustyluh": "Устилуг", 
    "Krakivets": "Краківець", 
    "Rava Ruska": "Рава-Руська", 
    "Shehyni": "Шегині", 
    "Uhryniv": "Угринів", 
    "Hrushiv": "Грушів", 
    "Nizhankovichi": "Нижанковичі", 
    "Smilnytsia": "Смільниця",
    "Malyi Bereznyi": "Малий Березний",
    "Uzhhorod": "Ужгород",
    "Kosyno": "Косино",
    "Chop": "Чоп (Тиса)",
    "Dzvinkove": "Дзвінкове",
    "Luzhanka": "Лужанка",
    "Vylok": "Вилок",
    "Velyka Palad": "Велика Паладь",
    "Orlivka": "Орлівка",
    "Dyakivtsi": "Дяківці",
    "Dyakove": "Дякове",
    "Krasnoilsk": "Красноїльськ",
    "Porubne": "Порубне",
    "Solotvyno": "Солотвино",
    "Reni": "Рені",
    "Mohyliv-Podilskyi": "Могилів-Подільський",
    "Bronnytsya": "Бронниця",
    "Rososhany": "Россошани",
    "Mamalyha": "Мамалига",
    "Sokyryany": "Сокиряни",
    "Mayaky-Udobne": "Маяки-Удобне",
    "Dolynske": "Долинське",
    "Starokozache": "Старокозаче",
    "Kelmentsi": "Кельменці",
    "Tabaky": "Табаки",
}

# Nested dictionary mapping: Ukrainian City -> Checkpoint -> Drive time (minutes)
DISTANCES_UA_TO_CP = {
    # Poland
    "Lviv": {
        "Ustyluh": 141, "Krakivets": 71, "Rava Ruska": 88, "Shehyni": 82, 
        "Uhryniv": 102, "Hrushiv": 78, "Nizhankovichi": 121, "Smilnytsia": 118,
        "Malyi Bereznyi": 206, "Uzhhorod": 246
    },
    "Lutsk": {"Ustyluh": 76, "Krakivets": 192, "Rava Ruska": 146, "Shehyni": 215, "Uhryniv": 103, "Hrushiv": 187, "Nizhankovichi": 251, "Smilnytsia": 249},
    "Kovel": {"Ustyluh": 49, "Krakivets": 194, "Rava Ruska": 135, "Shehyni": 226, "Uhryniv": 84, "Hrushiv": 180, "Nizhankovichi": 267, "Smilnytsia": 265},
    "Stryi": {"Ustyluh": 205, "Krakivets": 117, "Rava Ruska": 147, "Shehyni": 110, "Uhryniv": 165, "Hrushiv": 124, "Nizhankovichi": 113, "Smilnytsia": 110},
    "Brody": {"Ustyluh": 131, "Krakivets": 154, "Rava Ruska": 121, "Shehyni": 167, "Uhryniv": 93, "Hrushiv": 161, "Nizhankovichi": 202, "Smilnytsia": 200},
    # Slovakia, Hungary, Romania & Moldova
    "Mukachevo": {
        "Malyi Bereznyi": 72, "Uzhhorod": 42,
        "Kosyno": 44, "Chop": 43, "Dzvinkove": 51, "Luzhanka": 44, "Vylok": 55, "Velyka Palad": 79,
        "Orlivka": 800, "Dyakivtsi": 372, "Dyakove": 74, "Krasnoilsk": 367, "Porubne": 371, "Solotvyno": 128, "Reni": 776
    },
    "Uzhhorod": {
        "Malyi Bereznyi": 43, "Uzhhorod": 12,
        "Kosyno": 59, "Chop": 22, "Dzvinkove": 59, "Luzhanka": 68, "Vylok": 78, "Velyka Palad": 103
    },
    "Khust": {
        "Kosyno": 85, "Chop": 106, "Dzvinkove": 91, "Luzhanka": 70, "Vylok": 41, "Velyka Palad": 66
    },
    "Ivano-Frankivsk": {
        "Orlivka": 603, "Dyakivtsi": 175, "Dyakove": 239, "Krasnoilsk": 170, "Porubne": 174, "Solotvyno": 198, "Reni": 579
    },
    "Chernivtsi": {
        "Orlivka": 477, "Dyakivtsi": 45, "Dyakove": 359, "Krasnoilsk": 58, "Porubne": 43, "Solotvyno": 260, "Reni": 454
    },
    "Odesa": {
        "Orlivka": 207, "Dyakivtsi": 547, "Dyakove": 810, "Krasnoilsk": 603, "Porubne": 564, "Solotvyno": 766, "Reni": 230,
        "Mohyliv-Podilskyi": 381, "Bronnytsya": 378, "Rososhany": 475, "Mamalyha": 528, "Sokyryany": 436, "Mayaky-Udobne": 46,
        "Dolynske": 233, "Starokozache": 53, "Kelmentsi": 472, "Tabaky": 184
    },
    "Vinnytsia": {
        "Mohyliv-Podilskyi": 94, "Bronnytsya": 106, "Rososhany": 190, "Mamalyha": 244, "Sokyryany": 152, "Mayaky-Udobne": 343,
        "Dolynske": 438, "Starokozache": 345, "Kelmentsi": 192, "Tabaky": 410
    },
    "Uman": {
        "Mohyliv-Podilskyi": 223, "Bronnytsya": 229, "Rososhany": 310, "Mamalyha": 363, "Sokyryany": 271, "Mayaky-Udobne": 190,
        "Dolynske": 395, "Starokozache": 215, "Kelmentsi": 311, "Tabaky": 346
    },
}

# Nested dictionary mapping: Checkpoint -> Foreign City -> Drive time (minutes)
DISTANCES_CP_TO_PL = {
    # Poland
    "Ustyluh": {"Krakow": 269, "Warsaw": 227},
    "Krakivets": {"Krakow": 146, "Warsaw": 246},
    "Rava Ruska": {"Krakow": 211, "Warsaw": 241},
    "Shehyni": {"Krakow": 157, "Warsaw": 257},
    "Uhryniv": {"Krakow": 248, "Warsaw": 246},
    "Hrushiv": {"Krakow": 172, "Warsaw": 255},
    "Nizhankovichi": {"Krakow": 159, "Warsaw": 259},
    "Smilnytsia": {"Krakow": 204, "Warsaw": 304},
    # Slovakia
    "Malyi Bereznyi": {"Kosice": 85},
    "Uzhhorod": {"Kosice": 71},
    # Hungary
    "Kosyno": {"Budapest": 184},
    "Chop": {"Budapest": 181},
    "Dzvinkove": {"Budapest": 198},
    "Luzhanka": {"Budapest": 182},
    "Vylok": {"Budapest": 207},
    "Velyka Palad": {"Budapest": 220},
    # Romania
    "Orlivka": {"Bucharest": 207, "Constanta": 115},
    "Dyakivtsi": {"Bucharest": 386, "Constanta": 455},
    "Dyakove": {"Bucharest": 509, "Constanta": 614},
    "Krasnoilsk": {"Bucharest": 381, "Constanta": 450},
    "Porubne": {"Bucharest": 354, "Constanta": 423},
    "Solotvyno": {"Bucharest": 527, "Constanta": 633},
    "Reni": {"Bucharest": 198, "Constanta": 160},
    # Moldova
    "Mohyliv-Podilskyi": {"Chisinau": 173},
    "Bronnytsya": {"Chisinau": 174},
    "Rososhany": {"Chisinau": 186},
    "Mamalyha": {"Chisinau": 217},
    "Sokyryany": {"Chisinau": 187},
    "Mayaky-Udobne": {"Chisinau": 129},
    "Dolynske": {"Chisinau": 174},
    "Starokozache": {"Chisinau": 118},
    "Kelmentsi": {"Chisinau": 202},
    "Tabaky": {"Chisinau": 147},
}

def format_minutes_to_str(minutes: int) -> str:
    h = minutes // 60
    m = minutes % 60
    return f"{h}г {m}хв" if h else f"{m}хв"


# DB Checkpoint ID to internal CHECKPOINTS names mapping
DB_TO_INTERNAL_CP = {
    "PL_USTYLUH": "Ustyluh",
    "PL_KRAKOVETS": "Krakivets",
    "PL_RAVA": "Rava Ruska",
    "PL_SHEHYNI": "Shehyni",
    "PL_UHRYNIV": "Uhryniv",
    "PL_HRUSHIV": "Hrushiv",
    "PL_NIZHANKOVICHI": "Nizhankovichi",
    "PL_SMILNYTSIA": "Smilnytsia",
    "SK_MALYI_BEREZNYI": "Malyi Bereznyi",
    "SK_UZHHOROD": "Uzhhorod",
    "HU_KOSYNO": "Kosyno",
    "HU_CHOP": "Chop",
    "HU_DZVINKOVE": "Dzvinkove",
    "HU_LUZHANKA": "Luzhanka",
    "HU_VYLOK": "Vylok",
    "HU_VELYKA_PALAD": "Velyka Palad",
    "RO_PORUBNE": "Porubne",
    "RO_SOLOTVYNO": "Solotvyno",
    "RO_DIAKOVE": "Dyakove",
    "RO_DIAKIVTSI": "Dyakivtsi",
    "RO_KRASNOILSK": "Krasnoilsk",
    "RO_ORLIVKA": "Orlivka",
    "RO_RENI": "Reni",
    "MD_MOHYLIV": "Mohyliv-Podilskyi",
    "MD_BRONNYTSIA": "Bronnytsya",
    "MD_ROSSOSHANY": "Rososhany",
    "MD_MAMALYHA": "Mamalyha",
    "MD_SOKYRIANY": "Sokyryany",
    "MD_MAIAKY": "Mayaky-Udobne",
    "MD_DOLYNSKE": "Dolynske",
    "MD_STAROKOZACHE": "Starokozache",
    "MD_KELMENTSI": "Kelmentsi",
    "MD_TABAKY": "Tabaky",
}

# Reverse mapping: internal CHECKPOINTS name -> DB checkpoint_id
INTERNAL_TO_DB_CP = {internal: db_id for db_id, internal in DB_TO_INTERNAL_CP.items()}


async def get_checkpoint_wait_times(direction: str) -> dict:
    """Fetch average duration from checkpoint_status for the given direction."""
    try:
        result = await get_supabase().table("checkpoint_status") \
            .select("checkpoint_id, avg_duration_minutes") \
            .eq("direction", direction) \
            .eq("transport_type", "car") \
            .execute()
        
        stats = result.data or []
        wait_times = {}
        for row in stats:
            db_id = row["checkpoint_id"]
            if db_id in DB_TO_INTERNAL_CP:
                cp_name = DB_TO_INTERNAL_CP[db_id]
                wait_times[cp_name] = row["avg_duration_minutes"]
        return wait_times
    except Exception:
        logger.exception("Failed to fetch checkpoint wait times for route planning")
        return {}


async def handle_plan_route_cmd(chat_id: int):
    """Entry point for /plan_route -> choose country"""
    buttons = [
        [{"text": "Польща", "callback_data": "plan_country:PL"}],
        [{"text": "Словаччина", "callback_data": "plan_country:SK"}],
        [{"text": "Угорщина", "callback_data": "plan_country:HU"}],
        [{"text": "Румунія", "callback_data": "plan_country:RO"}],
        [{"text": "Молдова", "callback_data": "plan_country:MD"}],
        [{"text": CMD_CANCEL, "callback_data": "cancel:plan_country"}]
    ]
    await send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": "Оберіть країну:",
        "reply_markup": {"inline_keyboard": buttons},
    })


async def handle_plan_callback(chat_id: int, message_id: int, parts: list[str]):
    """State machine for the route planning flow."""
    action = parts[0]

    if action == "plan_country":
        country_code = parts[1] if len(parts) > 1 else "PL"
        await increment_plan_route_country_analytics(country_code)
        await increment_plan_route_funnel_analytics("step_1_country_selected")
        await send_telegram_request("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": "Оберіть напрямок руху:",
            "reply_markup": {"inline_keyboard": [
                [{"text": "🇪🇺 Виїзд з України", "callback_data": f"plan_dir:{country_code}:OUTBOUND"}],
                [{"text": "🇺🇦 В'їзд в Україну",  "callback_data": f"plan_dir:{country_code}:INBOUND"}],
                [{"text": CMD_CANCEL,              "callback_data": "cancel:plan_direction"}],
            ]},
        })

    elif action == "plan_dir":
        if len(parts) >= 3:
            country_code = parts[1]
            direction = parts[2]
        else:
            country_code = "PL"
            direction = parts[1]

        is_outbound = (direction == "OUTBOUND")
        await increment_plan_route_direction_analytics(country_code, direction)
        await increment_plan_route_funnel_analytics("step_2_direction_selected")
        
        cfg = COUNTRY_CONFIG.get(country_code, COUNTRY_CONFIG["PL"])
        prompt_text = "Оберіть ваше місто відправлення (Україна):" if is_outbound else f"Оберіть ваше місто відправлення ({cfg['name']}):"
        cities = cfg["ua_cities"] if is_outbound else cfg["foreign_cities"]

        buttons = []
        for city in cities:
            buttons.append([{"text": CITY_EN_TO_UA[city], "callback_data": f"plan_orig:{country_code}:{direction}:{city}"}])
        buttons.append([{"text": CMD_CANCEL, "callback_data": "cancel:plan_origin"}])

        await send_telegram_request("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": prompt_text,
            "reply_markup": {"inline_keyboard": buttons},
        })

    elif action == "plan_orig":
        if len(parts) >= 4:
            country_code = parts[1]
            direction = parts[2]
            origin_city = parts[3]
        else:
            country_code = "PL"
            direction = parts[1]
            origin_city = parts[2]

        is_outbound = (direction == "OUTBOUND")
        await increment_plan_route_city_analytics("origin", origin_city)
        await increment_plan_route_funnel_analytics("step_3_origin_selected")
        
        cfg = COUNTRY_CONFIG.get(country_code, COUNTRY_CONFIG["PL"])
        prompt_text = f"Оберіть ваше місто призначення ({cfg['name']}):" if is_outbound else "Оберіть ваше місто призначення (Україна):"
        cities = cfg["foreign_cities"] if is_outbound else cfg["ua_cities"]
        
        buttons = []
        for city in cities:
            buttons.append([{"text": CITY_EN_TO_UA[city], "callback_data": f"plan_dest:{country_code}:{direction}:{origin_city}:{city}"}])
        buttons.append([{"text": CMD_CANCEL, "callback_data": "cancel:plan_destination"}])

        await send_telegram_request("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": prompt_text,
            "reply_markup": {"inline_keyboard": buttons},
        })

    elif action == "plan_dest":
        if len(parts) >= 5:
            country_code = parts[1]
            direction = parts[2]
            origin_city = parts[3]
            destination_city = parts[4]
        else:
            country_code = "PL"
            direction = parts[1]
            origin_city = parts[2]
            destination_city = parts[3]

        await increment_plan_route_city_analytics("destination", destination_city)
        await increment_plan_route_funnel_analytics("step_4_completed")
        
        await send_telegram_request("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": "⏳ Розраховую найкращі маршрути...",
            "reply_markup": {}
        })

        wait_times = await get_checkpoint_wait_times(direction)
        raw_handles = await get_checkpoint_telegram_handles()
        handles = {
            DB_TO_INTERNAL_CP[db_id]: handle
            for db_id, handle in raw_handles.items()
            if db_id in DB_TO_INTERNAL_CP
        }
        closed_checkpoints = await get_closed_checkpoints()

        routes = []
        closed_names = []
        is_outbound = (direction == "OUTBOUND")
        ua_city = origin_city if is_outbound else destination_city
        foreign_city = destination_city if is_outbound else origin_city
        cfg = COUNTRY_CONFIG.get(country_code, COUNTRY_CONFIG["PL"])

        for cp in cfg["checkpoints"]:
            db_id = INTERNAL_TO_DB_CP.get(cp)
            if db_id in closed_checkpoints:
                closed_names.append(CHECKPOINT_EN_TO_UA.get(cp, cp))
                continue
            dist_ua = DISTANCES_UA_TO_CP.get(ua_city, {}).get(cp, 0)
            dist_pl = DISTANCES_CP_TO_PL.get(cp, {}).get(foreign_city, 0)
            
            # Use real-time wait from DB if available, else 0 or a small default
            wait_time = wait_times.get(cp, 0) 
            
            total_time = dist_ua + dist_pl + wait_time
            
            routes.append({
                "checkpoint": cp,
                "dist_ua": dist_ua,
                "dist_pl": dist_pl,
                "wait_time": wait_time,
                "total": total_time
            })
            
        # Sort by total time
        routes.sort(key=lambda x: x["total"])
        
        # Take top 3
        best_routes = routes[:3]
        
        direction_str = "Виїзд з України 🇪🇺" if is_outbound else "В'їзд в Україну 🇺🇦"
        lines = [
            f"🗺 <b>Оптимальні маршрути</b>",
            f"Напрямок: {direction_str}",
            f"Маршрут: <b>{CITY_EN_TO_UA[origin_city]} ➡️ {CITY_EN_TO_UA[destination_city]}</b>\n"
        ]

        if closed_names:
            lines.append(f"{CHECKPOINT_CLOSED_ICON} Закрито, не враховано в маршрутах: {', '.join(closed_names)}\n")

        if not best_routes:
            lines.append("😔 Усі пункти пропуску цього напрямку зараз закриті. Спробуйте інший напрямок або країну.")
            await send_telegram_request("sendMessage", {
                "chat_id": chat_id,
                "text": "\n".join(lines),
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "link_preview_options": {"is_disabled": True}
            })
            return

        for i, r in enumerate(best_routes, 1):
            cp_ua_name = CHECKPOINT_EN_TO_UA.get(r["checkpoint"], r["checkpoint"])
            handle = handles.get(r["checkpoint"])
            
            if handle:
                cp_display = f"<a href='https://t.me/{handle}'>{cp_ua_name}</a>"
            else:
                cp_display = cp_ua_name
                
            total_str = format_minutes_to_str(r["total"])
            drive_str = format_minutes_to_str(r["dist_ua"] + r["dist_pl"])
            wait_str = format_minutes_to_str(r["wait_time"])
            
            if r["wait_time"] == 0:
                wait_str = "немає свіжих даних (вважаємо 0)"
            
            lines.append(
                f"<b>{i}. через {cp_display}</b> — ⏱ <b>{total_str}</b>\n"
                f"   🚗 Їзда: {drive_str}\n"
                f"   🛂 Кордон: {wait_str}\n"
            )

        lines.append(f"📊 Точність цих прогнозів залежить від вас! Натисніть <b>{CMD_START_CROSSING}</b>, коли будете перетинати кордон, щоб зафіксувати свій час — це займає 10 секунд і допомагає іншим водіям планувати маршрут точніше.")
        lines.append("\n💡 Натисніть на назву пункту пропуску, щоб перейти в його чат.")

        await send_telegram_request("sendMessage", {
            "chat_id": chat_id,
            "text": "\n".join(lines),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "link_preview_options": {"is_disabled": True}
        })
