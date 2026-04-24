from fastapi import FastAPI, Request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from apscheduler.schedulers.background import BackgroundScheduler
import anthropic
import os

app = FastAPI()

# ดึงค่าจาก Environment Variables
line_bot_api = LineBotApi(os.environ["CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["CHANNEL_SECRET"])
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MY_USER_ID = os.environ["MY_USER_ID"]


def get_vocab_from_ai():
    """ให้ Claude สร้างคำศัพท์ใหม่ทุกวัน"""
    response = claude.messages.create(
        model="claude-opus-4-5",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": (
                "สร้างคำศัพท์ภาษาอังกฤษระดับ intermediate 1 คำ "
                "ตอบในรูปแบบนี้เท่านั้น ห้ามเพิ่มอะไรนอกจากนี้:\n\n"
                "WORD: (คำศัพท์)\n"
                "MEANING: (ความหมายภาษาไทย)\n"
                "EXAMPLE: (ประโยคตัวอย่างภาษาอังกฤษ)\n"
                "TIP: (เทคนิคจำคำนี้ภาษาไทย 1 ประโยค)"
            )
        }]
    )
    return response.content[0].text


def send_daily_vocab():
    """ส่งคำศัพท์เข้า LINE ทุกเช้า"""
    raw = get_vocab_from_ai()

    # แปลง text เป็น dict
    data = {}
    for line in raw.strip().split("\n"):
        if ": " in line:
            key, val = line.split(": ", 1)
            data[key.strip()] = val.strip()

    msg = (
        f"🌅 คำศัพท์ประจำวัน\n"
        f"━━━━━━━━━━━━━━\n"
        f"📖  {data.get('WORD', '—')}\n"
        f"🇹🇭  {data.get('MEANING', '—')}\n"
        f"💬  \"{data.get('EXAMPLE', '—')}\"\n"
        f"💡  {data.get('TIP', '—')}\n"
        f"━━━━━━━━━━━━━━\n"
        f"จำให้ได้ก่อนเที่ยงนะ! 💪"
    )

    line_bot_api.push_message(MY_USER_ID, TextSendMessage(text=msg))


# ตั้งเวลาส่งทุกเช้า 7:00 น. (เวลาไทย)
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
    text = event.message.text.strip().lower()

    if text in ["คำศัพท์", "vocab", "ขอคำศัพท์", "word"]:
        raw = get_vocab_from_ai()
        data = {}
        for line in raw.strip().split("\n"):
            if ": " in line:
                key, val = line.split(": ", 1)
                data[key.strip()] = val.strip()
        msg = (
            f"✨ คำศัพท์วันนี้\n"
            f"━━━━━━━━━━━━━━\n"
            f"📖  {data.get('WORD','—')}\n"
            f"🇹🇭  {data.get('MEANING','—')}\n"
            f"💬  \"{data.get('EXAMPLE','—')}\"\n"
            f"💡  {data.get('TIP','—')}\n"
            f"━━━━━━━━━━━━━━"
        )
    else:
        msg = (
            f"👋 สวัสดีครับ!\n\n"
            f"พิมพ์ได้เลยครับ:\n"
            f"• 'คำศัพท์' — ขอคำศัพท์ใหม่\n"
            f"• 'vocab' — ขอคำศัพท์ใหม่\n\n"
            f"หรือรอรับอัตโนมัติทุกเช้า 7:00 น. 🌅"
        )

    line_bot_api.reply_message(
        event.reply_token,
        TextSendM


@app.get("/")
def root():
    return {"status": "running"}
