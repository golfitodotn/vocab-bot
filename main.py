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

def get_used_words(user_id):
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        return [r["word"].lower() for r in records if str(r["user_id"]) == str(user_id)]
    except:
        return []

def get_word_count(user_id):
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        return len([r for r in records if str(r["user_id"]) == str(user_id)])
    except:
        return 0

def save_word(word, user_id):
    try:
        sheet = get_sheet()
        if sheet.row_count == 0 or sheet.cell(1, 1).value != "word":
            sheet.update("A1", [["word", "user_id"]])
        sheet.append_row([word, user_id])
    except:
        pass

SLEEPING_REPLIES = [
    "ประเทืองกำลังหลับ 😴 พิมพ์ 'word' เพื่อฉลาดขึ้น",
    "ประเทืองไม่ว่าง ไปท่องคำศัพท์ก่อนได้เลย 🙄",
    "อย่ามารบกวน ประเทืองฝันดีอยู่ 💤",
    "ประเทืองขอนอนก่อนนะ พิมพ์ 'word' ดีกว่า 😒",
    "ไม่รับสาย กรุณาโทรใหม่อีกครั้ง 📵",
    "ประเทืองไม่มีตัวตนในโลกนี้ชั่วคราว 🌙",
    "หยุดพิมพ์แล้วไปท่องคำศัพท์เถอะ 😤",
]

def get_vocab_from_ai(category="random", user_id=None):
    used_words = get_used_words(user_id) if user_id else []
    used_text = ", ".join(used_words[-50:]) if used_words else "ยังไม่มี"

    if category == "economics":
        topic = (
            "คำศัพท์ภาษาอังกฤษด้านเศรษฐศาสตร์ระดับ intermediate ขึ้นไป "
            "เช่น macroeconomics, monetary policy, fiscal policy, GDP, inflation "
            "เหมาะสำหรับเตรียมสอบ ป.โท economics"
        )
    elif category == "workplace":
        topic = (
            "คำศัพท์ภาษาอังกฤษที่ใช้ในที่ทำงานระดับ intermediate ขึ้นไป "
            "เช่น professional communication, business, management"
        )
    else:
        chosen = random.choice(["economics", "workplace"])
        return get_vocab_from_ai(chosen, user_id)

    response = claude.messages.create(
        model="claude-opus-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": (
            f"สร้างคำศัพท์ภาษาอังกฤษ 1 คำ ประเภท: {topic}\n"
            f"ห้ามใช้คำเหล่านี้ที่เคยส่งไปแล้ว: {used_text}\n"
            "ตอบในรูปแบบนี้เท่านั้น ห้ามเพิ่มอะไรนอกจากนี้:\n"
            "WORD: คำศัพท์\n"
            "MEANING: ความหมายภาษาไทย\n"
            "EXAMPLE: ประโยคตัวอย่าง\n"
            "TIP: เทคนิคจำ 1 ประโยค"
        )}]
    )
    return response.content[0].text

def get_greeting_from_ai():
    response = claude.messages.create(
        model="claude-opus-4-5",
        max_tokens=100,
        messages=[{"role": "user", "content": (
            "เขียนข้อความทักทายตอนเช้าภาษาไทยสั้นๆ แบบแฟนทักแฟน "
            "ให้หวานๆ อบอุ่น ไม่เกิน 2 บรรทัด "
            "ห้ามใช้ชื่อ ห้ามใส่ emoji มากเกิน 1 ตัว "
            "ให้แตกต่างกันทุกวัน"
        )}]
    )
    return response.content[0].text.strip()

def format_vocab(raw, user_id):
    data = {}
    for line in raw.strip().split("\n"):
        if ": " in line:
            key, val = line.split(": ", 1)
            data[key.strip()] = val.strip()
    word = data.get('WORD', '—')
    save_word(word, user_id)
    return (
        f"✨ คำศัพท์ประจำวัน\n"
        f"━━━━━━━━━━━━━━\n"
        f"📖 {word}\n"
        f"🇹🇭 {data.get('MEANING', '—')}\n"
        f"💬 {data.get('EXAMPLE', '—')}\n"
        f"💡 {data.get('TIP', '—')}\n"
        f"━━━━━━━━━━━━━━"
    )

def send_daily_vocab():
    uids = []
    if os.environ.get("MY_USER_ID"):
        uids.append(os.environ.get("MY_USER_ID"))
    if os.environ.get("FRIEND_USER_ID"):
        uids.append(os.environ.get("FRIEND_USER_ID"))
    if not uids:
        return
    greeting = get_greeting_from_ai()
    for uid in uids:
        vocab = format_vocab(get_vocab_from_ai("random", uid), uid)
        msg = f"{greeting}\n\n{vocab}"
        line_bot_api.push_message(uid, TextSendMessage(text=msg))

def send_reminder():
    uids = []
    if os.environ.get("MY_USER_ID"):
        uids.append(os.environ.get("MY_USER_ID"))
    if os.environ.get("FRIEND_USER_ID"):
        uids.append(os.environ.get("FRIEND_USER_ID"))
    if not uids:
        return
    msg = "อย่าลืมทวนศัพท์นะ 📚\nแล้วก็เลิกเล่น TikTok ได้แล้ว ประเทืองแสบตา 👁️"
    for uid in uids:
        line_bot_api.push_message(uid, TextSendMessage(text=msg))

scheduler = BackgroundScheduler(timezone="Asia/Bangkok")
scheduler.add_job(send_daily_vocab, "cron", hour=7, minute=0)
scheduler.add_job(send_reminder, "cron", hour=21, minute=0)
scheduler.start()

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
        reply = format_vocab(get_vocab_from_ai("random", uid), uid)
    elif text == "econ":
        reply = format_vocab(get_vocab_from_ai("economics", uid), uid)
    elif text == "work":
        reply = format_vocab(get_vocab_from_ai("workplace", uid), uid)
    elif text == "นับ":
        count = get_word_count(uid)
        reply = f"📊 คุณเรียนไปแล้ว {count} คำแล้วนะ เก่งมาก! 🎉"
    elif text == "myid":
        reply = f"User ID ของคุณ:\n{uid}"
    elif text in ["help", "ช่วยเหลือ", "คำสั่ง"]:
        reply = (
            "📋 คำสั่งทั้งหมดของประเทือง\n"
            "━━━━━━━━━━━━━━\n"
            "📖 word — ขอคำศัพท์สุ่ม\n"
            "📊 econ — คำศัพท์เศรษฐศาสตร์\n"
            "💼 work — คำศัพท์ทำงาน\n"
            "🔢 นับ — ดูว่าเรียนไปกี่คำแล้ว\n"
            "🆔 myid — ดู User ID ของคุณ\n"
            "━━━━━━━━━━━━━━\n"
            "⏰ ประเทืองส่งคำศัพท์ให้ทุกเช้า 7:00 น.\n"
            "🌙 แล้วก็จะทวงให้ทวนศัพท์ตอน 3 ทุ่มด้วยนะ 😏"
        )
    else:
        reply = random.choice(SLEEPING_REPLIES)

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.get("/")
def root():
    return {"status": "running"}
