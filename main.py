from fastapi import FastAPI, Request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from apscheduler.schedulers.background import BackgroundScheduler
import anthropic, os

app = FastAPI()

line_bot_api = LineBotApi(os.environ["CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["CHANNEL_SECRET"])
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def get_vocab_from_ai():
    response = claude.messages.create(
        model="claude-opus-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": (
            "สร้างคำศัพท์ภาษาอังกฤษระดับ intermediate 1 คำ "
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
        f"📖 {data.get('WORD','—')}\n"
        f"🇹🇭 {data.get('MEANING','—')}\n"
        f"💬 {data.get('EXAMPLE','—')}\n"
        f"💡 {data.get('TIP','—')}\n"
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
    else:
        reply = "👋 สวัสดีครับ!\nพิมพ์ 'คำศัพท์' เพื่อขอคำศัพท์ใหม่ได้เลยครับ 😊"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.get("/")
def root():
    return {"status": "running"}
