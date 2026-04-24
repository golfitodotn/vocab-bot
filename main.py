from fastapi import FastAPI, Request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from apscheduler.schedulers.background import BackgroundScheduler
import anthropic, os, random, gspread
from google.oauth2.service_account import Credentials

app = FastAPI()

# ===== เชื่อมต่อ LINE และ Claude =====
# LineBotApi = ใช้ส่งข้อความออก
# WebhookHandler = ใช้รับข้อความเข้า
# anthropic.Anthropic = ใช้คุยกับ Claude AI
line_bot_api = LineBotApi(os.environ["CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["CHANNEL_SECRET"])
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ===== GOOGLE SHEETS =====
def get_sheet():
    # สร้าง credentials จาก environment variables
    # ใช้ service account แทน OAuth เพราะไม่ต้อง login
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
    # .sheet1 = เข้าถึง sheet แรกของ spreadsheet
    return client.open_by_key(os.environ["GOOGLE_SHEET_ID"]).sheet1

def get_user_data(user_id):
    # ดึงข้อมูลครั้งเดียวแล้วใช้ทั้ง used_words และ count
    # ประหยัดกว่าเรียก 2 ฟังก์ชันแยกกัน = ลด API call ของ Google
    try:
        records = get_sheet().get_all_records()
        # filter เฉพาะ records ของ user คนนั้น
        user_records = [r for r in records if str(r["user_id"]) == str(user_id)]
        words = [r["word"].lower() for r in user_records]
        return words, len(words)  # return tuple (list of words, count)
    except:
        return [], 0  # ถ้า error ให้ return ค่าเริ่มต้น

def save_word(word, user_id):
    # บันทึกคำศัพท์ที่ส่งแล้วลง Google Sheets
    # เพื่อป้องกันคำซ้ำในครั้งต่อไป
    try:
        get_sheet().append_row([word, user_id])
    except:
        pass  # ถ้า error ให้ข้ามไป ไม่ให้ bot crash

# ===== ข้อความสุ่มตอบเวลาพิมพ์นอกเหนือคำสั่ง =====
# random.choice() จะสุ่มเลือก 1 ข้อความจาก list นี้
# ไม่เรียก AI = ฟรี 100%
SLEEPING_REPLIES = [
    "ประเทืองกำลังหลับอยู่นะ 😴\nพิมพ์ help ดูคำสั่งได้เลย",
    "ไม่ว่างจ้า ไปท่องศัพท์ก่อนเลย 🙄",
    "อย่ามารบกวน กำลังฝันดีอยู่ 💤",
    "ขอนอนก่อนนะ พิมพ์ word ดีกว่า 😒",
    "ไม่มีตัวตนในโลกนี้ชั่วคราว 🌙",
    "หยุดพิมพ์ แล้วไปท่องศัพท์เถอะนะ 😤",
]

# ===== AI FUNCTIONS =====
def get_vocab_from_ai(category="random", user_id=None):
    # ดึงคำที่เคยส่งไปแล้วของ user คนนั้น
    # เพื่อบอก Claude ว่าห้ามใช้คำพวกนี้
    used_words, _ = get_user_data(user_id) if user_id else ([], 0)
    # เอาแค่ 50 คำล่าสุด เพื่อไม่ให้ prompt ยาวเกินไป = ประหยัด token
    used_text = ", ".join(used_words[-100:]) if used_words else "ยังไม่มี"

    if category == "economics":
        topic = (
            "เศรษฐศาสตร์ระดับ intermediate-advanced "
            "เช่น monetary policy, fiscal policy, GDP, inflation, elasticity "
            "เหมาะเตรียม ป.โท economics"
        )
    elif category == "workplace":
        topic = (
            "การทำงานระดับ intermediate-advanced "
            "เช่น negotiation, delegation, stakeholder, productivity"
        )
    else:
        # สุ่มระหว่าง economics และ workplace
        return get_vocab_from_ai(random.choice(["economics", "workplace"]), user_id)

    response = claude.messages.create(
        # ใช้ Haiku แทน Opus = ถูกกว่า 10x เพียงพอสำหรับสร้างคำศัพท์
        # Haiku: ~$0.00025/request vs Opus: ~$0.015/request
        model="claude-haiku-4-5-20251001",
        max_tokens=250,  # จำกัด token = ประหยัดค่าใช้จ่าย
        messages=[{"role": "user", "content": (
            f"สร้างคำศัพท์ภาษาอังกฤษ 1 คำ หมวด: {topic}\n"
            f"ห้ามใช้คำเหล่านี้: {used_text}\n"
            "ตอบแค่นี้เท่านั้น:\n"
            "WORD: คำ\n"
            "MEANING: ความหมายไทย\n"
            "EXAMPLE: ประโยคสั้นๆ\n"
            "TIP: เทคนิคจำ 1 ประโยค"
        )}]
    )
    return response.content[0].text

def get_greeting_from_ai():
    response = claude.messages.create(
        model="claude-haiku-4-5-20251001",  # Haiku เพียงพอสำหรับทักทาย
        max_tokens=80,  # ข้อความสั้น max_tokens น้อย = ประหยัดกว่า
        messages=[{"role": "user", "content": (
            "ทักทายตอนเช้าแบบแฟนทักแฟน ภาษาไทย หวานๆ ไม่เกิน 2 บรรทัด "
            "ห้ามใช้ชื่อ emoji ได้ 1 ตัว ให้ต่างกันทุกวัน"
        )}]
    )
    return response.content[0].text.strip()

def format_vocab(raw, user_id):
    # แปลง text จาก Claude เป็น Dictionary
    # เช่น "WORD: Resilient" → data["WORD"] = "Resilient"
    data = {}
    for line in raw.strip().split("\n"):
        if ": " in line:
            key, val = line.split(": ", 1)
            data[key.strip()] = val.strip()
    word = data.get("WORD", "—")
    # บันทึกคำลง Google Sheets ทันทีหลังได้คำ
    save_word(word, user_id)
    # จัดรูปแบบข้อความให้อ่านง่ายใน LINE
    return (
        f"✨ คำศัพท์วันนี้\n"
        f"─────────────\n"
        f"📖  {word}\n"
        f"🇹🇭  {data.get('MEANING', '—')}\n\n"
        f"💬  {data.get('EXAMPLE', '—')}\n\n"
        f"💡  {data.get('TIP', '—')}\n"
        f"─────────────"
    )

# ===== SCHEDULERS =====
def send_daily_vocab():
    # รวบรวม user IDs ที่ต้องส่ง
    # filter(None, ...) กรองค่า None ออก กรณีไม่ได้ตั้ง FRIEND_USER_ID
    uids = [uid for uid in [
        os.environ.get("MY_USER_ID"),
        os.environ.get("FRIEND_USER_ID")
    ] if uid]
    if not uids:
        return
    # เรียก greeting ครั้งเดียว แต่ vocab แยกแต่ละ user
    # เพื่อให้แต่ละคนได้คำไม่ซ้ำกัน
    greeting = get_greeting_from_ai()
    for uid in uids:
        vocab = format_vocab(get_vocab_from_ai("random", uid), uid)
        line_bot_api.push_message(uid, TextSendMessage(text=f"{greeting}\n\n{vocab}"))

def send_reminder():
    uids = [uid for uid in [
        os.environ.get("MY_USER_ID"),
        os.environ.get("FRIEND_USER_ID")
    ] if uid]
    if not uids:
        return
    for uid in uids:
        # ดึงจำนวนคำของแต่ละ user แยกกัน
        _, count = get_user_data(uid)
        msg = (
            f"🌙 ใกล้ดึกแล้วนะ\n"
            f"─────────────\n"
            f"อย่าลืมทวนศัพท์ก่อนนอนด้วยล่ะ 📚\n"
            f"แล้วก็เลิกเล่น ทส ได้แล้วประเทืองแสบตา 👁️\n\n"
            f"📊 เรียนสะสมไปแล้ว {count} คำ\n"
            f"ขยันต่อไปนะ เก่งมากเลย 💪"
        )
        line_bot_api.push_message(uid, TextSendMessage(text=msg))

# ตั้งเวลา scheduler
# cron = ทำงานตามเวลาที่กำหนด เหมือน alarm
scheduler = BackgroundScheduler(timezone="Asia/Bangkok")
scheduler.add_job(send_daily_vocab, "cron", hour=7, minute=0)   # ทุกเช้า 7:00
scheduler.add_job(send_reminder, "cron", hour=21, minute=0)     # ทุกคืน 3 ทุ่ม
scheduler.start()

# ===== WEBHOOK =====
@app.post("/webhook")
async def webhook(request: Request):
    # รับ request จาก LINE server
    # signature ใช้ verify ว่า request มาจาก LINE จริงๆ ไม่ใช่คนอื่น
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")
    handler.handle(body.decode(), signature)
    return {"status": "ok"}

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    uid = event.source.user_id       # User ID ของคนที่ส่งมา
    text = event.message.text.strip().lower()  # แปลงเป็นตัวเล็กหมด เพื่อ match ง่าย

    if text in ["คำศัพท์", "vocab", "word", "ขอคำศัพท์"]:
        # สุ่มระหว่าง econ และ work
        reply = format_vocab(get_vocab_from_ai("random", uid), uid)

    elif text == "econ":
        # เจาะจงเฉพาะคำศัพท์เศรษฐศาสตร์
        reply = format_vocab(get_vocab_from_ai("economics", uid), uid)

    elif text == "work":
        # เจาะจงเฉพาะคำศัพท์การทำงาน
        reply = format_vocab(get_vocab_from_ai("workplace", uid), uid)

    elif text == "นับ":
        # ดึงจำนวนคำของ user คนนั้น
        # _ คือ used_words ที่ไม่ได้ใช้ในกรณีนี้
        _, count = get_user_data(uid)
        reply = (
            f"📊 สถิติของคุณ\n"
            f"─────────────\n"
            f"เรียนสะสมไปแล้ว {count} คำ\n"
            f"เก่งมากเลยนะ! 🎉"
        )

    elif text == "myid":
        reply = f"🆔 User ID ของคุณ\n{uid}"

    elif text in ["help", "ช่วยเหลือ", "คำสั่ง"]:
        # ไม่เรียก AI = ฟรี
        reply = (
            "📋 คำสั่งของประเทือง\n"
            "─────────────\n"
            "word  —  คำศัพท์สุ่ม\n"
            "econ  —  คำศัพท์เศรษฐศาสตร์\n"
            "work  —  คำศัพท์ทำงาน\n"
            "นับ    —  ดูสถิติของคุณ\n"
            "─────────────\n"
            "⏰  ส่งคำศัพท์ทุกเช้า 7:00 น.\n"
            "🌙  ทวงให้ทวนศัพท์ทุก 3 ทุ่ม"
        )

    else:
        # ไม่เรียก AI = ฟรี สุ่มข้อความกวนตีน
        reply = random.choice(SLEEPING_REPLIES)

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.get("/")
def root():
    return {"status": "running"}
