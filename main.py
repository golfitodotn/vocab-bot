from fastapi import FastAPI, Request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from apscheduler.schedulers.background import BackgroundScheduler
import anthropic, os, random, gspread
import google.generativeai as genai
from google.oauth2.service_account import Credentials

app = FastAPI()

line_bot_api = LineBotApi(os.environ["CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["CHANNEL_SECRET"])
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
gemini = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

# ===== KEYWORD เช็คว่าเพื่อนพูดถึงเจ้าของไหม =====
# แก้ให้ตรงกับชื่อที่เพื่อนใช้เรียกคุณได้เลย
OWNER_KEYWORDS = ["แฟน", "เขา", "นาย", "golf", "กอล์ฟ","พี่","คิดถึง","คถ","กอฟ","พ่อ","ป่ะปี๊" ]

def is_mentioning_owner(text):
    return any(kw in text.lower() for kw in OWNER_KEYWORDS)

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
    try:
        records = get_sheet().get_all_records()
        user_records = [r for r in records if str(r["user_id"]) == str(user_id)]
        words = [r["word"].lower() for r in user_records]
        return words, len(words)
    except:
        return [], 0

def save_word(word, user_id):
    try:
        get_sheet().append_row([word, user_id])
    except:
        pass

# ===== ข้อความ auto สำรอง =====
SLEEPING_REPLIES = [
    "ประเทืองหลับอยู่งับ 😴 พิมพ์ help ดูคำสั่งได้เลยงับ",
    "ไม่ว่างงับ ไปท่องศัพท์ก่อนเลยงับ 🙄",
    "อย่ามารบกวนเลยงับ กำลังฝันดีอยู่เยยย 💤",
    "ขอนอนก่อนนะงับ พิมพ์ word ดีกว่า 😒",
    "ไม่มีตัวตนในโลกนี้ชั่วคราวงับ 🌙",
    "หยุดพิมพ์ได้แล้วไปท่องศัพท์เถอะนะ 😤",
]

# ===== AI FUNCTIONS =====
def get_vocab_from_ai(category="random", user_id=None):
    used_words, _ = get_user_data(user_id) if user_id else ([], 0)
    used_text = ", ".join(used_words) if used_words else "ยังไม่มี"

    if category == "economics":
        topic = (
            "เศรษฐศาสตร์และการเงินระดับ intermediate-advanced "
            "เช่น monetary policy, fiscal policy, GDP, inflation, elasticity, "
            "derivatives, portfolio, liquidity, hedge fund, yield curve, "
            "quantitative easing, asset allocation "
            "เหมาะเตรียม ป.โท economics และงานด้านการเงิน"
        )
    elif category == "workplace":
        topic = (
            "การทำงานในออฟฟิศและการสื่อสารระดับ intermediate-advanced "
            "เช่น คำที่ใช้ในอีเมลธุรกิจ เช่น pursuant to, per our discussion, "
            "as per your request, kindly revert, loop in, touch base, "
            "take this offline, circle back, deliverable, bandwidth, "
            "escalate, stakeholder, actionable, synergy "
            "เหมาะสำหรับการทำงานในออฟฟิศและส่งอีเมลระดับมืออาชีพ"
        )
    else:
        return get_vocab_from_ai(random.choice(["economics", "workplace"]), user_id)

    try:
        prompt = (
            f"สร้างคำศัพท์ภาษาอังกฤษ 1 คำ หมวด: {topic}\n"
            f"ห้ามใช้คำเหล่านี้: {used_text}\n"
            "ตอบแค่นี้เท่านั้น ห้ามเพิ่มอะไรนอกจากนี้:\n"
            "WORD: คำ\n"
            "MEANING: ความหมายไทย\n"
            "EXAMPLE: ประโยคสั้นๆ\n"
            "TIP: เทคนิคจำ 1 ประโยค"
        )
        response = gemini.generate_content(prompt)
        return response.text
    except:
        return "ประเทืองหมดคำจะพูด -.-"

def get_greeting_from_ai():
    try:
        response = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content": (
                "ทักทายตอนเช้าแบบแฟนทักแฟน ภาษาไทย หวานๆ ไม่เกิน 2 บรรทัด "
                "ห้ามใช้ชื่อ emoji ได้ 1 ตัว ให้ต่างกันทุกวัน "
                "พูดแบ้วๆ ลงท้ายด้วย งับ หรือ เยย หรือ แง้วๆ "
                "ห้ามใช้ # ** _ หรือ Markdown ใดๆ ทั้งสิ้น "
                "ตอบเป็นข้อความธรรมดาเท่านั้น"
            )}]
        )
        return response.content[0].text.strip()
    except:
        return "อรุณสวัสดิ์งับ 🌅 วันนี้ก็ขยันเรียนด้วยน้าาาา"

def get_chat_reply(text):
    try:
        response = gemini.generate_content(
            f"คุณชื่อประเทือง พูดแบ้วๆ ตอบสั้นๆ ไม่เกิน 2 บรรทัด "
            f"กวนตีนนิดหน่อยแต่น่ารักไม่พูดคำหยาบ "
            f"เหมือนคุยกับแฟน "
            f"ตอบข้อความนี้เป็นภาษาไทย: {text}"
        )
        return response.text.strip()
    except:
        return random.choice(SLEEPING_REPLIES)

def format_vocab(raw, user_id):
    if "หมดคำจะพูด" in raw:
        return raw
    data = {}
    for line in raw.strip().split("\n"):
        if ": " in line:
            key, val = line.split(": ", 1)
            data[key.strip()] = val.strip()
    word = data.get("WORD", "—")
    if word != "—":
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
        _, count = get_user_data
