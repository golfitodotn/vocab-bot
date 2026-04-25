from fastapi import FastAPI, Request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from apscheduler.schedulers.background import BackgroundScheduler
import anthropic, os, random, gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
gemini = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

app = FastAPI()

line_bot_api = LineBotApi(os.environ["CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["CHANNEL_SECRET"])
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ===== KEYWORDS =====
OWNER_KEYWORDS = ["แฟน", "เขา", "นาย", "golf", "กอล์ฟ", "พี่", "คิดถึง", "คถ", "กอฟ", "พ่อ", "ป่ะปี๊", "ปะปี๊"]
MOOD_KEYWORDS = ["งอล", "งอน", "โกรธ", "โกด", "โมโห", "น้อยใจ", "ซึม"]

def is_mentioning_owner(text):
    return any(kw in text.lower() for kw in OWNER_KEYWORDS)

def is_bad_mood(text):
    return any(kw in text.lower() for kw in MOOD_KEYWORDS)

# ===== GOOGLE SHEETS =====
_sheet_cache = None
_data_cache = {}

def get_sheet():
    global _sheet_cache
    if _sheet_cache is not None:
        return _sheet_cache
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
    _sheet_cache = client.open_by_key(os.environ["GOOGLE_SHEET_ID"]).sheet1
    return _sheet_cache

def get_user_data(user_id):
    if user_id in _data_cache:
        words = _data_cache[user_id]
        return words, len(words)
    try:
        records = get_sheet().get_all_records()
        user_records = [r for r in records if str(r["user_id"]) == str(user_id)]
        words = [r["word"].lower() for r in user_records]
        _data_cache[user_id] = words
        return words, len(words)
    except:
        return [], 0

def save_word(word, user_id, meaning=""):
    try:
        get_sheet().append_row([word, user_id, meaning])
        if user_id in _data_cache:
            _data_cache[user_id].append(word.lower())
    except:
        pass

def get_vocab_history(user_id):
    try:
        records = get_sheet().get_all_records()
        user_records = [r for r in records if str(r["user_id"]) == str(user_id)]
        return [(r.get("word", ""), r.get("meaning", "")) for r in user_records if r.get("word")]
    except:
        return []

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
            "escalate, stakeholder, actionable, synergy"
        )
    else:
        return get_vocab_from_ai(random.choice(["economics", "workplace"]), user_id)

    try:
        response = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": (
                f"สร้างคำศัพท์ภาษาอังกฤษ 1 คำ หมวด: {topic}\n"
                f"ห้ามใช้คำเหล่านี้: {used_text}\n"
                "ตอบแค่นี้เท่านั้น ห้ามเพิ่มอะไรนอกจากนี้:\n"
                "WORD: คำ\n"
                "MEANING: ความหมายไทย\n"
                "EXAMPLE: ประโยคสั้นๆ\n"
                "TIP: เทคนิคจำ 1 ประโยค"
            )}]
        )
        return response.content[0].text
    except:
        return "ประเทืองหมดคำจะพูด -.-"

def get_greeting_from_ai():
    try:
        response = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content": (
                "คุณคือลูกชื่อประเทือง กำลังคุยทักทายแม่ตอนเช้าแบบอ้อนๆ ภาษาไทย หวานๆ ไม่เกิน 2 บรรทัด "
                "ห้ามใช้ชื่อ emoji ได้ 1 ตัว ให้ต่างกันทุกวัน "
                "พูดแบ้วๆเหมือนอ้อนแม่เริ่มต้นว่า มอนิ่งงับ แทนตัวเองว่าผม "
                "ห้ามใช้ # ** _ หรือ Markdown ใดๆ ทั้งสิ้น "
                "ตอบเป็นข้อความธรรมดาเท่านั้น"
            )}]
        )
        return response.content[0].text.strip()
    except:
        return "อรุณสวัสดิ์งับ 🌅 วันนี้ก็ขยันเรียนด้วยน้าาาา"

def get_chat_reply(text, uid):
    my_uid = os.environ.get("MY_USER_ID")
    friend_uid = os.environ.get("FRIEND_USER_ID")

    if uid == my_uid:
        persona = (
            "คุณคือลูกชื่อประเทืองเป็นผู้ชาย กำลังคุยกับพ่อ "
            "แทนตัวเองว่าผม ตอบสั้นๆ ไม่เกิน 2 บรรทัด "
            "พูดเพราะกวนนิดหน่อยแต่น่ารักไม่พูดคำหยาบ "
            "เข้าข้างพ่อเสมอ ถ้าพ่อบ่นอะไรให้เห็นด้วย "
            "ห้ามใช้ Markdown ตอบเป็นข้อความธรรมดา"
        )
    elif uid == friend_uid:
        persona = (
            "คุณคือลูกชื่อประเทืองเป็นผู้ชาย กำลังคุยกับแม่ "
            "แทนตัวเองว่าผม ตอบสั้นๆ ไม่เกิน 2 บรรทัด "
            "พูดเพราะกวนนิดหน่อยแต่น่ารักไม่พูดคำหยาบ "
            "รักแม่นะแต่ขอเข้าข้างพ่อมากกว่านิดนึง 😅 "
            "ห้ามใช้ Markdown ตอบเป็นข้อความธรรมดา"
        )
    else:
        persona = (
            "คุณชื่อประเทือง เป็นตัวแทนของลูก แทนตัวเองว่าผม "
            "พูดแบ้วๆ กวนตีนนิดหน่อยแต่น่ารัก ไม่พูดคำหยาบ "
            "ลงท้ายด้วย งับ ห้ามใช้ Markdown"
        )

    try:
        response = gemini.generate_content(
            f"{persona}\nตอบข้อความนี้เป็นภาษาไทย: {text}"
        )
        return response.text.strip()
    except:
        return "ประเทืองเหนื่อย หมดคำจะพูด -.-"

def format_vocab(raw, user_id):
    if "หมดคำจะพูด" in raw:
        return raw
    data = {}
    for line in raw.strip().split("\n"):
        if ": " in line:
            key, val = line.split(": ", 1)
            data[key.strip()] = val.strip()
    word = data.get("WORD", "—")
    meaning = data.get("MEANING", "—")
    if word != "—":
        save_word(word, user_id, meaning)
    return (
        f"✨ คำศัพท์วันนี้\n"
        f"─────────────\n"
        f"📖  {word}\n"
        f"🇹🇭  {meaning}\n\n"
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
        _, count = get_user_data(uid)
        msg = (
            f"🌙 ใกล้ดึกแล้วงับ\n"
            f"─────────────\n"
            f"อย่าลืมทวนศัพท์ก่อนนอนด้วยน้าาา 📚\n"
            f"แล้วก็เลิกเล่น ทส ได้แล้วงับ แสบตา\n\n"
            f"📊 เรียนสะสมไปแล้ว {count} คำแล้วงับ\n"
            f"ขยันมากเยยยยย 💪"
        )
        line_bot_api.push_message(uid, TextSendMessage(text=msg))

scheduler = BackgroundScheduler(timezone="Asia/Bangkok")
scheduler.add_job(send_daily_vocab, "cron", hour=7, minute=0)
scheduler.add_job(send_reminder, "cron", hour=21, minute=0)
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
    my_uid = os.environ.get("MY_USER_ID")
    friend_uid = os.environ.get("FRIEND_USER_ID")

    # เช็คเฉพาะ FRIEND_USER_ID เท่านั้น
    if uid == friend_uid and friend_uid and my_uid:

        # เช็คอารมณ์ก่อน — priority สูงสุด
        if is_bad_mood(text):
            line_bot_api.push_message(
                my_uid,
                TextSendMessage(
                    text=(
                        f"🚨 คุณพ่อ RED CODE RED CODE 🚨\n"
                        f"─────────────\n"
                        f"แม่พูดว่า: \"{event.message.text}\""
                    )
                )
            )
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="ประเทืองจะนำส่งเรื่องให้คุณชายงับ 📨")
            )
            return

        # เช็คว่าพูดถึงพ่อไหม
        if is_mentioning_owner(text):
            bot_reply = get_chat_reply(event.message.text, uid)
            line_bot_api.push_message(
                my_uid,
                TextSendMessage(
                    text=(
                        f"🔔 เห้ยเขาพูดถึงนายอะ!\n"
                        f"─────────────\n"
                        f"แม่พูดว่า: \"{event.message.text}\"\n\n"
                        f"ประเทืองตอบว่า: \"{bot_reply}\""
                    )
                )
            )
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=bot_reply)
            )
            return

    if text in ["คำศัพท์", "vocab", "word", "ขอคำศัพท์"]:
        category = random.choices(["workplace", "economics"], weights=[80, 20])[0]
        reply = format_vocab(get_vocab_from_ai(category, uid), uid)

    elif text == "econ":
        reply = format_vocab(get_vocab_from_ai("economics", uid), uid)

    elif text == "work":
        reply = format_vocab(get_vocab_from_ai("workplace", uid), uid)

    elif text in ["ประวัติ", "history"]:
        history = get_vocab_history(uid)
        if not history:
            reply = "ยังไม่มีคำศัพท์ในประวัติงับ ลองพิมพ์ word ก่อนเลยงับ 😊"
        else:
            recent = history[-10:]
            lines = [f"📚 คำศัพท์ที่เรียนไปแล้ว ({len(history)} คำ)\n─────────────"]
            for i, (word, meaning) in enumerate(reversed(recent), 1):
                lines.append(f"{i}. {word} — {meaning}")
            reply = "\n".join(lines)

    elif text == "testmorning":
        greeting = get_greeting_from_ai()
        category = random.choices(["workplace", "economics"], weights=[80, 20])[0]
        vocab = format_vocab(get_vocab_from_ai(category, uid), uid)
        reply = f"{greeting}\n\n{vocab}"

    elif text == "testreminder":
        _, count = get_user_data(uid)
        reply = (
            f"🌙 ใกล้ดึกแล้วงับ\n"
            f"─────────────\n"
            f"อย่าลืมทวนศัพท์ก่อนนอนด้วยน้าาา 📚\n"
            f"แล้วก็เลิกเล่น ทส ได้แล้วงับ แสบตา\n\n"
            f"📊 เรียนสะสมไปแล้ว {count} คำแล้วงับ\n"
            f"ขยันมากเยยยยย 💪"
        )

    elif text == "นับ":
        _, count = get_user_data(uid)
        reply = (
            f"📊 สถิติของนาย\n"
            f"─────────────\n"
            f"เรียนสะสมไปแล้ว {count} คำแล้วงับ\n"
            f"เก่งมากเยยยย 🎉"
        )

    elif text == "myid":
        reply = f"🆔 User ID ของคุณงับ\n{uid}"

    elif text in ["help", "ช่วยเหลือ", "คำสั่ง"]:
        reply = (
            "📋 คำสั่งของประเทืองงับ\n"
            "─────────────\n"
            "word      —  คำศัพท์สุ่ม\n"
            "econ      —  คำศัพท์เศรษฐศาสตร์\n"
            "work      —  คำศัพท์ทำงาน\n"
            "ประวัติ   —  ดูคำศัพท์ที่เรียนไปแล้ว\n"
            "นับ       —  ดูสถิติของคุณ\n"
            "─────────────\n"
            "⏰  ส่งคำศัพท์ทุกเช้า 7:00 น. งับ\n"
            "🌙  ทวงให้ทวนศัพท์ทุก 3 ทุ่มงับ"
        )

    else:
        use_claude = random.choices([True, False], weights=[70, 30])[0]
        if use_claude:
            reply = get_chat_reply(text, uid)
        else:
            reply = random.choice(SLEEPING_REPLIES)

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.get("/")
def root():
    return {"status": "running"}
