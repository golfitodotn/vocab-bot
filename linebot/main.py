from fastapi import FastAPI, Request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from apscheduler.schedulers.background import BackgroundScheduler
import anthropic
import os

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
            "ตอบในรูปแบบนี้เท่านั้น:\n\n"
            "WORD: (คำศัพท์)\nMEANING: (ความหมายภาษาไทย)\n"
            "EXAMPLE: (ประโยคตัวอย่าง)\nTIP: (เทคนิคจำ 1 ประโยค)"
        )}]
    )
    return response.content[0].text

def send_daily_vocab():
    my_user_id = os.environ.get("MY_USER_ID", "")
    if not my_user_id or my_user_id == "temp":
        return
    raw = get_vocab_from_ai()
    data = {}
    for line in raw.strip().split("\n"):
        if ": " in line:
            key, val = line.split(": ", 1)
            data[key.strip()] = val.strip()
    msg = (
        f"🌅 คำศัพท์ประจำวัน\n━━━━━━━━━━━━━━\n"
        f"📖  {data.get('WORD','—')}\n🇹🇭  {data.get('MEANING','—')}\n"
        f"💬  \"{data.get('EXAMPLE','—')}\"\n💡  {data.get('TIP','—')}\n"
        f"━━━━━━━━━━━━━━\nจำให้ได้ก่อนเที่ยงนะ! 💪"
    )
    line_bot_api.push_message(my_user_id, TextSendMessage(text=msg))

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
    uid = event.source.user_id
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=f"✅ Bot พร้อมแล้ว!\nUser ID ของคุณ:\n{uid}")
    )

@app.get("/")
def root():
    return {"status": "running"}
