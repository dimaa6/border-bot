import logging
from datetime import datetime, timezone
from clients import get_supabase, send_telegram_request
from constants import CMD_CANCEL
from db_helpers import get_checkpoint_telegram_handles

logger = logging.getLogger(__name__)

# Internal lists used by the system (English keys)
UKRAINIAN_CITIES = ["Lviv", "Lutsk", "Kovel", "Stryi", "Brody"]
POLISH_CITIES = ["Krakow", "Warsaw"]
CHECKPOINTS = [
    "Ustyluh", "Krakivets", "Rava Ruska", "Shehyni", 
    "Uhryniv", "Hrushiv", "Nizhankovichi", "Smilnytsia"
]

# Translation mappings: English -> Ukrainian
CITY_EN_TO_UA = {
    "Lviv": "Львів",
    "Lutsk": "Луцьк",
    "Kovel": "Ковель",
    "Stryi": "Стрий",
    "Brody": "Броди",
    "Krakow": "Краків",
    "Warsaw": "Варшава"
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
    "Smilnytsia": "Смільниця"
}

# Nested dictionary mapping: Ukrainian City -> Checkpoint -> Drive time (minutes)
DISTANCES_UA_TO_CP = {
    "Lviv": {"Ustyluh": 141, "Krakivets": 71, "Rava Ruska": 88, "Shehyni": 82, "Uhryniv": 102, "Hrushiv": 78, "Nizhankovichi": 121, "Smilnytsia": 118},
    "Lutsk": {"Ustyluh": 76, "Krakivets": 192, "Rava Ruska": 146, "Shehyni": 215, "Uhryniv": 103, "Hrushiv": 187, "Nizhankovichi": 251, "Smilnytsia": 249},
    "Kovel": {"Ustyluh": 49, "Krakivets": 194, "Rava Ruska": 135, "Shehyni": 226, "Uhryniv": 84, "Hrushiv": 180, "Nizhankovichi": 267, "Smilnytsia": 265},
    "Stryi": {"Ustyluh": 205, "Krakivets": 117, "Rava Ruska": 147, "Shehyni": 110, "Uhryniv": 165, "Hrushiv": 124, "Nizhankovichi": 113, "Smilnytsia": 110},
    "Brody": {"Ustyluh": 131, "Krakivets": 154, "Rava Ruska": 121, "Shehyni": 167, "Uhryniv": 93, "Hrushiv": 161, "Nizhankovichi": 202, "Smilnytsia": 200},
}

# Nested dictionary mapping: Checkpoint -> Polish City -> Drive time (minutes)
DISTANCES_CP_TO_PL = {
    "Ustyluh": {"Krakow": 269, "Warsaw": 227},
    "Krakivets": {"Krakow": 146, "Warsaw": 246},
    "Rava Ruska": {"Krakow": 211, "Warsaw": 241},
    "Shehyni": {"Krakow": 157, "Warsaw": 257},
    "Uhryniv": {"Krakow": 248, "Warsaw": 246},
    "Hrushiv": {"Krakow": 172, "Warsaw": 255},
    "Nizhankovichi": {"Krakow": 159, "Warsaw": 259},
    "Smilnytsia": {"Krakow": 204, "Warsaw": 304},
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
}


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
        [{"text": CMD_CANCEL, "callback_data": "cancel:flow"}]
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
        # country_code = parts[1] # only PL supported right now
        await send_telegram_request("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": "Оберіть напрямок руху:",
            "reply_markup": {"inline_keyboard": [
                [{"text": "🇪🇺 Виїзд з України", "callback_data": "plan_dir:OUTBOUND"}],
                [{"text": "🇺🇦 В'їзд в Україну",  "callback_data": "plan_dir:INBOUND"}],
                [{"text": CMD_CANCEL,              "callback_data": "cancel:flow"}],
            ]},
        })

    elif action == "plan_dir":
        direction = parts[1]
        is_outbound = (direction == "OUTBOUND")
        
        prompt_text = "Оберіть ваше місто відправлення (Україна):" if is_outbound else "Оберіть ваше місто відправлення (Польща):"
        cities = UKRAINIAN_CITIES if is_outbound else POLISH_CITIES

        buttons = []
        for city in cities:
            buttons.append([{"text": CITY_EN_TO_UA[city], "callback_data": f"plan_orig:{direction}:{city}"}])
        buttons.append([{"text": CMD_CANCEL, "callback_data": "cancel:flow"}])

        await send_telegram_request("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": prompt_text,
            "reply_markup": {"inline_keyboard": buttons},
        })

    elif action == "plan_orig":
        direction = parts[1]
        origin_city = parts[2]
        is_outbound = (direction == "OUTBOUND")
        
        prompt_text = "Оберіть ваше місто призначення (Польща):" if is_outbound else "Оберіть ваше місто призначення (Україна):"
        cities = POLISH_CITIES if is_outbound else UKRAINIAN_CITIES
        
        buttons = []
        for city in cities:
            buttons.append([{"text": CITY_EN_TO_UA[city], "callback_data": f"plan_dest:{direction}:{origin_city}:{city}"}])
        buttons.append([{"text": CMD_CANCEL, "callback_data": "cancel:flow"}])

        await send_telegram_request("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": prompt_text,
            "reply_markup": {"inline_keyboard": buttons},
        })

    elif action == "plan_dest":
        direction = parts[1]
        origin_city = parts[2]
        destination_city = parts[3]
        
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
        
        routes = []
        is_outbound = (direction == "OUTBOUND")
        ua_city = origin_city if is_outbound else destination_city
        pl_city = destination_city if is_outbound else origin_city

        for cp in CHECKPOINTS:
            dist_ua = DISTANCES_UA_TO_CP.get(ua_city, {}).get(cp, 0)
            dist_pl = DISTANCES_CP_TO_PL.get(cp, {}).get(pl_city, 0)
            
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
            
        lines.append("💡 Натисніть на назву пункту пропуску, щоб перейти в його чат.")
            
        await send_telegram_request("sendMessage", {
            "chat_id": chat_id,
            "text": "\n".join(lines),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "link_preview_options": {"is_disabled": True}
        })
