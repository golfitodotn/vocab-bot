"""
calorie.py — Image Calorie Tracker for ประเทือง Bot
แยก user ด้วย uid, เก็บข้อมูลสำคัญครบใน Google Sheets

Sheet structure (tab "Calories"):
  col A: uid          — LINE user id
  col B: date         — YYYY-MM-DD
  col C: time         — HH:MM
  col D: meal_type    — เช้า / กลางวัน / ของว่าง / เย็น
  col E: food_name    — ชื่ออาหาร
  col F: calories     — kcal (int)
  col G: protein_g    — กรัม
  col H: carb_g       — กรัม
  col I: fat_g        — กรัม
  col J: note         — หมายเหตุจาก AI
"""

import os
import base64
import json
import requests
import anthropic
import gspread
from datetime import datetime, timezone, timedelta
from google.oauth2.service_account import Credentials
from linebot.models import TextSendMessage

# ── Timezone Bangkok ──────────────────────────────────────────────────────────
BKK = timezone(timedelta(hours=7))

def now_bkk():
    return datetime.now(BKK)

def get_meal_type() -> str:
    """ระบุมื้ออาหารจากเวลาปัจจุบัน"""
    hour = now_bkk().hour
    if 5 <= hour < 10:
        return "เช้า"
    elif 10 <= hour < 14:
        return "กลางวัน"
    elif 14 <= hour < 17:
        return "ของว่าง"
    elif 17 <= hour < 22:
        return "เย็น"
    else:
        return "ของว่าง"

# ── Claude client ─────────────────────────────────────────────────────────────
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ── Google Sheets ─────────────────────────────────────────────────────────────
SHEET_HEADERS = [
    "uid", "date", "time", "meal_type",
    "food_name", "calories", "protein_g", "carb_g", "fat_g", "note"
]

_calorie_sheet_cache = None

def get_calorie_sheet():
    """Cache sheet connection — connect ครั้งเดียว ไม่ช้า"""
    global _calorie_sheet_cache
    if _calorie_sheet_cache is not None:
        return _calorie_sheet_cache

    try:
        creds = Credentials.from_service_account_info(
            {
                "type": "service_account",
                "private_key": os.environ["GOOGLE_PRIVATE_KEY"].replace("\\n", "\n"),
                "client_email": os.environ["GOOGLE_CLIENT_EMAIL"],
                "token_uri": "https://oauth2.googleapis.com/token",
            },
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(os.environ["GOOGLE_SHEET_ID"])

        # สร้าง tab "Calories" ถ้ายังไม่มี
        try:
            sheet = spreadsheet.worksheet("Calories")
        except gspread.WorksheetNotFound:
            sheet = spreadsheet.add_worksheet(title="Calories", rows="2000", cols="10")
            sheet.append_row(SHEET_HEADERS)

        _calorie_sheet_cache = sheet
        return sheet

    except Exception as e:
        print(f"[calorie] Sheet error: {e}")
        return None


def log_calorie(uid: str, data: dict) -> bool:
    """
    บันทึก 1 row ต่อมื้อ แยก user ด้วย uid
    data keys: food_name, calories, protein_g, carb_g, fat_g, note
    """
    sheet = get_calorie_sheet()
    if sheet is None:
        return False

    now = now_bkk()
    row = [
        uid,
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M"),
        get_meal_type(),
        data.get("food_name", "ไม่ทราบ"),
        data.get("calories", 0),
        data.get("protein_g", 0),
        data.get("carb_g", 0),
        data.get("fat_g", 0),
        data.get("note", ""),
    ]

    try:
        sheet.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        print(f"[calorie] Log error: {e}")
        return False


def get_user_records(uid: str, date_str: str = None) -> list:
    """ดึง records ของ uid เฉพาะ (filter by date ถ้าส่งมา)"""
    sheet = get_calorie_sheet()
    if sheet is None:
        return []

    try:
        all_records = sheet.get_all_records()
        records = [r for r in all_records if str(r.get("uid", "")) == uid]
        if date_str:
            records = [r for r in records if str(r.get("date", "")) == date_str]
        return records
    except Exception as e:
        print(f"[calorie] Fetch records error: {e}")
        return []


def safe_int(val) -> int:
    try:
        return int(str(val).replace(",", "").strip())
    except Exception:
        return 0


# ── วิเคราะห์รูปอาหารด้วย Claude Vision ──────────────────────────────────────
def analyze_food_image(image_bytes: bytes, content_type: str = "image/jpeg") -> dict:
    """
    ส่งรูปให้ Claude Haiku วิเคราะห์
    return dict: food_name, calories, protein_g, carb_g, fat_g, note
               หรือ {"error": "not_food"} / {"error": "..."}
    """
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    prompt = """วิเคราะห์อาหารในรูปนี้ ตอบเป็น JSON เท่านั้น ห้ามมี text อื่น ไม่ต้องมี markdown

ถ้าเป็นอาหาร:
{
  "food_name": "ชื่ออาหาร ภาษาไทย",
  "calories": 450,
  "protein_g": 25,
  "carb_g": 55,
  "fat_g": 12,
  "note": "ค่าประมาณ 1 จาน หมายเหตุสั้นๆ ภาษาไทย"
}

ถ้าไม่ใช่รูปอาหาร:
{"error": "not_food"}

กฎสำคัญ:
- calories, protein_g, carb_g, fat_g ต้องเป็น integer เท่านั้น ห้ามมี unit
- ประมาณจากปริมาณเฉลี่ย 1 จาน / 1 ที่"""

    try:
        response = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=250,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": content_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": prompt}
                ],
            }],
        )

        raw = response.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)

    except json.JSONDecodeError as e:
        print(f"[calorie] JSON parse error: {e}")
        return {"error": "parse_error"}
    except Exception as e:
        print(f"[calorie] Analyze error: {e}")
        return {"error": str(e)}


# ── Format ข้อความ ────────────────────────────────────────────────────────────
def format_calorie_reply(result: dict, uid: str) -> str:
    """ข้อความตอบกลับหลังวิเคราะห์รูป"""
    if "error" in result:
        if result["error"] == "not_food":
            return "อ้าว นั่นไม่ใช่รูปอาหารนี่งับ 😅\nลองส่งรูปอาหารมาใหม่นะงับ 📸"
        return "วิเคราะห์ไม่ได้งับ รูปอาจไม่ชัด ลองถ่ายใหม่นะ 📸"

    food = result.get("food_name", "ไม่ทราบ")
    cal  = result.get("calories", 0)
    pro  = result.get("protein_g", 0)
    carb = result.get("carb_g", 0)
    fat  = result.get("fat_g", 0)
    note = result.get("note", "")
    meal = get_meal_type()

    # ดึงแคลวันนี้รวม (หลัง log แล้ว จะรวม row นี้ด้วย)
    today = now_bkk().strftime("%Y-%m-%d")
    records = get_user_records(uid, today)
    total_cal = sum(safe_int(r.get("calories", 0)) for r in records)
    meal_count = len(records)

    reply = (
        f"🍽️ {food}  ({meal})\n"
        f"─────────────\n"
        f"🔥 {cal} kcal\n"
        f"💪 โปรตีน {pro}g  🍚 คาร์บ {carb}g  🧈 ไขมัน {fat}g\n"
    )
    if note:
        reply += f"📝 {note}\n"
    reply += (
        f"─────────────\n"
        f"วันนี้รวม: {total_cal} kcal  ({meal_count} มื้อ)\n"
        f"พิมพ์ 'แคลวันนี้' ดูรายละเอียดงับ 📊"
    )
    return reply


def format_today_summary(uid: str) -> str:
    """สรุปแคลทั้งหมดของ user วันนี้"""
    today = now_bkk().strftime("%Y-%m-%d")
    records = get_user_records(uid, today)

    if not records:
        return (
            "ยังไม่มีข้อมูลวันนี้เลยงับ 😴\n"
            "ส่งรูปอาหารมาสิ ประเทืองจะนับแคลให้งับ 📸"
        )

    total_cal  = sum(safe_int(r.get("calories", 0)) for r in records)
    total_pro  = sum(safe_int(r.get("protein_g", 0)) for r in records)
    total_carb = sum(safe_int(r.get("carb_g", 0)) for r in records)
    total_fat  = sum(safe_int(r.get("fat_g", 0)) for r in records)

    lines = []
    for r in records:
        lines.append(
            f"  {r.get('time','')}  {r.get('meal_type','')}  "
            f"{r.get('food_name','')}  ({r.get('calories',0)} kcal)"
        )

    return (
        f"📊 แคลวันนี้ของนาย\n"
        f"─────────────\n"
        + "\n".join(lines) +
        f"\n─────────────\n"
        f"รวม  🔥 {total_cal} kcal\n"
        f"💪 {total_pro}g  🍚 {total_carb}g  🧈 {total_fat}g\n"
        f"({len(records)} มื้อ) งับ"
    )


# ── Handlers (เรียกจาก main.py) ───────────────────────────────────────────────
def handle_image_calorie(event, line_bot_api, line_headers: dict):
    """
    วางใน main.py:

        from linebot.models import ImageMessage
        from calorie import handle_image_calorie, handle_calorie_text

        LINE_HEADERS = {"Authorization": f"Bearer {os.environ['LINE_CHANNEL_ACCESS_TOKEN']}"}

        @handler.add(MessageEvent, message=ImageMessage)
        def on_image(event):
            handle_image_calorie(event, line_bot_api, LINE_HEADERS)

        # ใน handle_message() วางก่อน else:
        elif text in ["แคลวันนี้", "แคล", "calorie"]:
            reply = handle_calorie_text(event.source.user_id)
    """
    uid = event.source.user_id
    message_id = event.message.id

    # โหลดรูปจาก LINE
    try:
        url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"
        resp = requests.get(url, headers=line_headers, timeout=15)
        resp.raise_for_status()
        image_bytes = resp.content
        content_type = resp.headers.get("Content-Type", "image/jpeg")
    except Exception as e:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="โหลดรูปไม่ได้งับ ลองใหม่นะ 😅")
        )
        print(f"[calorie] Fetch image error: {e}")
        return

    # วิเคราะห์
    result = analyze_food_image(image_bytes, content_type)

    # บันทึกลง Sheets ก่อน format (ให้ total รวม row ปัจจุบันด้วย)
    if "error" not in result:
        log_calorie(uid, result)

    reply = format_calorie_reply(result, uid)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))


def handle_calorie_text(uid: str) -> str:
    """เรียกเมื่อ user พิมพ์ 'แคลวันนี้'"""
    return format_today_summary(uid)
