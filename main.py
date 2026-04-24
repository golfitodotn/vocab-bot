from fastapi import FastAPI, Request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from apscheduler.schedulers.background import BackgroundScheduler
import anthropic, os, random, gspread
from google.oauth2.service_account import Credentials

app = FastAPI()

line_bot_api = LineBotApi(os.environ["CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["CHANNEL_SECRET"])
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ===== GOOGLE SHEETS =====
def get_sheet():
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
    return client.open_by_key(os.environ["GOOGLE_SHEET_ID"]).sheet1

def get_user_data(user_id):
    # ดึงข้อมูลครั้งเดียว ได้ทั้ง used_words และ count
    try:
        records = get_sheet().get_all_records()
        user_records = [r for r in records if str(r["user_id"]) == str(user_id)]
        words = [r["word"].lower() for r in user_records]
        return words, len(words)
    except:
        return [], 0

def save_word(word, user_id):
    # บันทึกคำใหม่ลง Google Sheets เพื่อป้องกันซ้ำ
    try:
        get_sheet().append_row([word, user_id])
    except:
        pass

# ===== ข้อความสุ่มตอบ — ไม่เรียก AI = ฟรี =====
SLEEPING_REPLIES = [
    "ประเทืองหลับอยู่งับ 😴 พิมพ์ help ดูคำสั่งได้เลยงับ",
    "ไม่ว่างงับ ไปท่องศัพท์ก่อนเลยงับ 🙄",
    "อย่ามารบกวนเลยงับ กำลังฝันดีอยู่เลย 💤",
    "ขอนอนก่อนนะงับ พิมพ์ word ดีกว่างับ 😒",
    "ไม่มีตัวตนในโลกนี้ชั่วคราวงับ 🌙",
    "หยุดพิมพ์ได้แล้วงับ ไปท่องศัพท์เถอะนะงับ 😤",
]

# ===== AI FUNCTIONS =====
def get_vocab_from_ai(category="random", user_id=None):
    used_words, _ = get_user_data(user_id) if user_id else ([], 0)
    # ส่ง 100 คำล่าสุด เพื่อป้องกันซ้ำ แต่ไม่ให้ prompt ยาวเกิน
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
        # random สุ่มระหว่าง econ และ work
        return get_vocab_from_ai(random.choice(["economics", "workplace"]), user_id)

    response = claude.messages.create(
        # Haiku = ถูกกว่า Opus 10x เพียงพอสำหรับสร้างคำศัพท์
        model="claude-haiku-4-5-20251001",
        max_tokens=250,  # จำกัด token = ประหยัด
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
        max_tokens=80,  # ข้อความสั้น max_tokens น้อย = ประหยัด
        messages=[{"role": "user", "content": (
            "ทักทายตอนเช้าแบบแฟนทักแฟน ภาษาไทย หวานๆ ไม่เกิน 2 บรรทัด "
            "ห้ามใช้ชื่อ emoji ได้ 1 ตัว ให้ต่างกันทุกวัน "
            "พูดแบ้วๆ ลงท้ายด้วย งับ หรือ เยย หรือ แง้วๆ"
        )}]
    )
    return response.content[0].text.strip()

def format_vocab(raw, user_id):
    # แปลง text จาก Claude → Dictionary แล้วจัดหน้าตาให้อ่านง่าย
    data = {}
    for line in raw.strip().split("\n"):
        if ": " in line:
            key, val = line.split(": ", 1)
            data[key.strip()] = val.strip()
    word = data.get("WORD", "—")
    save_word(word, user_id)
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
    uids = [uid for uid in [
        os.environ.get("MY_USER_ID"),
        os.environ.get("FRIEND_USER_ID")
    ] if uid]
    if not uids:
        return
    greeting = get_greeting_from_ai()
    for uid in uids:
        # work 80% econ 20% โดยใช้ random.choices
        # weights=[80, 20] = สัดส่วนที่ต้องการ
        category = random.choices(
            ["workplace", "economics"],
            weights=[80, 20]
        )[0]
        vocab = format_vocab(get_vocab_from_ai(category, uid), uid)
        line_bot_api.push_message(uid, TextSendMessage(text=f"{greeting}\n\n{vocab}"))

def send_reminder():
    uids = [uid for uid in [
        os.environ.get("MY_USER_ID"),
        os.environ.get("FRIEND_USER_ID")
    ] if uid]
    if not uids:
        return
    for uid in uids:
        _, count = get_user_data(uid)
        msg = (
            f"🌙 ใกล้ดึกแล้วงับ\n"
            f"─────────────\n"
            f"อย่าลืมทวนศัพท์ก่อนนอนด้วยนะงับ 📚\n"
            f"แล้วก็เลิกเล่น TikTok ได้แล้วงับ แสบตาเลยงับ 👁️\n\n"
            f"📊 เรียนสะสมไปแล้ว {count} คำแล้วงับ\n"
            f"เยยยย ขยันมากเลยงับ 💪"
        )
        line_bot_api.push_message(uid, TextSendMessage(text=msg))

# cron = ทำงานตามเวลาที่กำหนด
scheduler = BackgroundScheduler(timezone="Asia/Bangkok")
scheduler.add_job(send_daily_vocab, "cron", hour=7, minute=0)   # ทุกเช้า 7:00
scheduler.add_job(send_reminder, "cron", hour=21, minute=0)     # ทุกคืน 3 ทุ่ม
scheduler.start()

# ===== WEBHOOK =====
@app.post("/webhook")
async def webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")
    handler.handle(body.decode(), signature)
    return {"status": "ok"}

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    uid = event.source.user_id
    text = event.message.text.strip().lower()

    if text in ["คำศัพท์", "vocab", "word", "ขอคำศัพท์"]:
        # สุ่ม 50/50 เมื่อขอเอง
        reply = format_vocab(get_vocab_from_ai("random", uid), uid)

    elif text == "econ":
        reply = format_vocab(get_vocab_from_ai("economics", uid), uid)

    elif text == "work":
        reply = format_vocab(get_vocab_from_ai("workplace", uid), uid)

    elif text == "นับ":
        _, count = get_user_data(uid)
        reply = (
            f"📊 สถิติของคุณงับ\n"
            f"─────────────\n"
            f"เรียนสะสมไปแล้ว {count} คำแล้วงับ\n"
            f"เยยยย เก่งมากเลยงับ 🎉"
        )

    elif text == "myid":
        reply = f"🆔 User ID ของคุณงับ\n{uid}"

    elif text in ["help", "ช่วยเหลือ", "คำสั่ง"]:
        # ไม่เรียก AI = ฟรี
        reply = (
            "📋 คำสั่งของประเทืองงับ\n"
            "─────────────\n"
            "word  —  คำศัพท์สุ่มงับ\n"
            "econ  —  คำศัพท์เศรษฐศาสตร์งับ\n"
            "work  —  คำศัพท์ทำงานงับ\n"
            "นับ    —  ดูสถิติของคุณงับ\n"
            "─────────────\n"
            "⏰  ส่งคำศัพท์ทุกเช้า 7:00 น. งับ\n"
            "🌙  ทวงให้ทวนศัพท์ทุก 3 ทุ่มงับ"
        )

    else:
        # ไม่เรียก AI = ฟรี
        reply = random.choice(SLEEPING_REPLIES)

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.get("/")
def root():
    return {"status": "running"}
