from fastapi import FastAPI, Request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from apscheduler.schedulers.background import BackgroundScheduler
import anthropic, os, random

app = FastAPI()

line_bot_api = LineBotApi(os.environ["CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["CHANNEL_SECRET"])
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SLEEPING_REPLIES = [
    "ประเทืองกำลังหลับ 😴 พิมพ์ 'vocab' เพื่อฉลาดขึ้น",
    "ประเทืองไม่ว่าง ไปท่องคำศัพท์ก่อนได้เลย 🙄",
    "อย่ามารบกวน ประเทืองฝันดีอยู่ 💤",
    "ประเทืองขอนอนก่อนนะ พิมพ์ 'word' ดีกว่า 😒",
    "ไม่รับสาย กรุณาโทรใหม่อีกครั้ง 📵",
    "ประเทืองไม่มีตัวตนในโลกนี้ชั่วคราว 🌙",
    "หยุดพิมพ์แล้วไปท่องคำศัพท์เถอะ 😤",
]

def get_vocab_from_ai():
    category = random.choice(["economics", "workplace"])
    if category == "economics":
        topic = (
            "คำศัพท์ภาษาอังกฤษด้านเศรษฐศาสตร์ระดับ graduate "
            "เช่น macroeconomics, monetary policy, fiscal policy, GDP, inflation "
            "เหมาะสำหรับเตรียมสอบ ป.โท economics"
        )
    else:
        topic = (
            "คำศัพท์ภาษาอังกฤษที่ใช้ในที่ทำงานระดับ intermediate-advanced "
            "เช่น professional communication, business, management"
        )
    response = claude.messages.create(
        model="claude-opus-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": (
            f"สร้างคำศัพท์ภาษาอังกฤษ 1 คำ ประเภท: {topic}\n"
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

def format_vocab(raw):
    data = {}
    for line in raw.strip().split("\n"):
        if ": " in line:
            key, val = line.split(": ", 1)
            data[key.strip()] = val.strip()
    return (
        f"✨ คำศัพท์ประจำวัน\n"
        f"━━━━━━━━━━━━━━\n"
        f"📖 {data.get('WORD', '—')}\n"
        f"🇹🇭 {data.get('MEANING', '—')}\n"
        f"💬 {data.get('EXAMPLE', '—')}\n"
        f"💡 {data.get('TIP', '—')}\n"
        f"━━━━━━━━━━━━━━"
    )

def send_daily_vocab():
    uid = os.environ.get("MY_USER_ID", "")
    if not uid or uid == "temp":
        return
    greeting = get_greeting_from_ai()
    vocab = format_vocab(get_vocab_from_ai())
    msg = f"{greeting}\n\n{vocab}"
    line_bot_api.push_message(uid, TextSendMessage(text=msg))

scheduler = BackgroundScheduler(timezone="Asia/Bangkok")
scheduler.add_job(send_daily_vocab, "cron", hour=7, minute=0)
scheduler.start()

@app.post("/webhook")
async def webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")
    handler.handle(body.decode(), signature)
    return {"status": "ok"}

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip().lower()
    if text in ["คำศัพท์", "vocab", "word", "ขอคำศัพท์"]:
        reply = format_vocab(get_vocab_from_ai())
    elif text == "myid":
        reply = f"User ID ของคุณ:\n{event.source.user_id}"
    else:
        reply = random.choice(SLEEPING_REPLIES)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.get("/")
def root():
    return {"status": "running"}
