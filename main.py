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
    "ประเทืองกำลังหลับ 😴 พิมพ์ 'word' เพื่อฉลาดขึ้น",
    "ประเทืองไม่ว่าง ไปท่องคำศัพท์ก่อนได้เลย 🙄",
    "อย่ามารบกวน ประเทืองฝันดีอยู่ 💤",
    "ประเทืองขอนอนก่อนนะ พิมพ์ 'word' ดีกว่า 😒",
    "ไม่รับสาย กรุณาโทรใหม่อีกครั้ง 📵",
    "ประเทืองไม่มีตัวตนในโลกนี้ชั่วคราว 🌙",
    "หยุดพิมพ์แล้วไปท่องคำศัพท์เถอะ 😤",
]

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
        model="claude-opus
