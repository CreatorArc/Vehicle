import os
import re
import time
import sqlite3
import threading
import uuid
import requests
from flask import Flask
import telebot
from telebot import types

# ----------------- FLASK SERVER FOR RENDER -----------------
app = Flask('')

@app.route('/')
def home():
    return "Vehicle RC Finder Bot is running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask).start()

# ----------------- CONFIGURATION -----------------
BOT_TOKEN = "8834683428:AAGlWn91Xj4UjCu6pEVyuLoSWaU_SLjmS00"
ADMIN_ID = 8800158361

VEHICLE_API = "https://vehicle-chass.vercel.app/api/vehicle?rc="
UPI_QR_PHOTO_URL = "https://t.me/shjahshsbsb/5"
UPI_ID = "paytmqr2810050501011gv6cueh16my@paytm"

bot = telebot.TeleBot(BOT_TOKEN)
bot.remove_webhook()
waiting_screenshot = set()

# ----------------- DATABASE SETUP -----------------
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        credits INTEGER DEFAULT 0
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS coupons (
        code TEXT PRIMARY KEY,
        points INTEGER,
        is_used INTEGER DEFAULT 0
    )
""")
conn.commit()

def get_user_credits(user_id):
    cursor.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute("INSERT INTO users (user_id, credits) VALUES (?, ?)", (user_id, 0))
        conn.commit()
        return 0
    return row[0]

def update_user_credits(user_id, delta):
    current = get_user_credits(user_id)
    new_bal = max(0, current + delta)
    cursor.execute("UPDATE users SET credits = ? WHERE user_id = ?", (new_bal, user_id))
    conn.commit()
    return new_bal

# ----------------- VEHICLE API FUNCTIONS -----------------
def safe_get(d, key, default='N/A'):
    val = d.get(key, '')
    return default if (val == '' or val is None) else str(val)

def get_vehicle_data(rc):
    try:
        response = requests.get(VEHICLE_API + rc, timeout=25)
        data = response.json()
        if not data.get('success', False):
            return None, None

        v = data.get('vehicle', {})
        s = data.get('specifications', {})
        ins = data.get('insurance', {})
        addr = data.get('address', {})
        pol = data.get('pollution', {})

        chassis = s.get('Chassis Number', '')
        if not chassis:
            return None, None

        reg = {
            'reg_no': v.get('Registration Number', ''),
            'owner': v.get('Owner', ''),
            'father': v.get('Father Name', ''),
            'owner_type': v.get('Owner Type', ''),
            'status': v.get('Status', ''),
            'reg_authority': v.get('Registration Authority', ''),
            'reg_date': v.get('Registration Date', ''),
            'rc_expiry': v.get('RC Expiry', ''),
            'manufacturer': s.get('Manufacturer', ''),
            'model': s.get('Model', ''),
            'vehicle_class': s.get('Vehicle Class', ''),
            'fuel': s.get('Fuel Type', ''),
            'engine': s.get('Engine Number', ''),
            'chassis': chassis,
            'ins_company': ins.get('Company', ''),
            'ins_policy': ins.get('Policy Number', ''),
            'ins_valid': ins.get('Valid Till', ''),
            'pucc_valid': pol.get('PUCC Valid Till', ''),
            'present_addr': addr.get('Present Address', ''),
            'perm_addr': addr.get('Permanent Address', '')
        }
        return chassis[-5:], reg
    except Exception:
        return None, None

def get_mobile(rc, last5):
    session = requests.Session()
    BASE = {'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-US,en;q=0.9'}
    HP = 'https://vahan.parivahan.gov.in/vahanservice/vahan/ui/statevalidation/homepage.xhtml?statecd=Mzc2MzM2MzAzNjY0MzIzODM3NjIzNjY0MzY2MjM3NDQ0Yw=='
    HB = 'https://vahan.parivahan.gov.in/vahanservice/vahan/ui/statevalidation/homepage.xhtml'
    LI = 'https://vahan.parivahan.gov.in/vahanservice/vahan/ui/usermgmt/login.xhtml'
    FR = 'https://vahan.parivahan.gov.in/vahanservice/vahan/ui/balanceservice/form_reschedule_fitness.xhtml'

    for attempt in range(2):
        try:
            r = session.get(HP, headers=BASE, timeout=25)
            vs = re.search(r'<input[^>]*name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', r.text)
            if not vs:
                continue
            vs = vs.group(1)

            AH = {'Accept': 'application/xml, text/xml, */*; q=0.01', 'Content-Type': 'application/x-www-form-urlencoded', 'Faces-Request': 'partial/ajax', 'X-Requested-With': 'XMLHttpRequest', 'Origin': 'https://vahan.parivahan.gov.in', 'Referer': HP}
            r = session.post(HB, headers=AH, data={'javax.faces.partial.ajax': 'true', 'javax.faces.source': 'fit_c_office_to', 'javax.faces.partial.execute': 'fit_c_office_to', 'javax.faces.behavior.event': 'change', 'homepageformid': 'homepageformid', 'fit_c_office_to_input': '1', 'javax.faces.ViewState': vs}, timeout=20)
            m = re.search(r'<update id="j_id1:javax\.faces\.ViewState:0"><!\[CDATA\[(.*?)\]\]></update>', r.text)
            if m: vs = m.group(1)

            r = session.post(HB, headers=AH, data={'javax.faces.partial.ajax': 'true', 'javax.faces.source': 'proccedHomeButtonId', 'javax.faces.partial.execute': '@all', 'proccedHomeButtonId': 'proccedHomeButtonId', 'homepageformid': 'homepageformid', 'j_idt193_input': 'on', 'javax.faces.ViewState': vs}, timeout=20)
            m = re.search(r'<update id="j_id1:javax\.faces\.ViewState:0"><!\[CDATA\[(.*?)\]\]></update>', r.text)
            if m: vs = m.group(1)

            r = session.post(HB, headers=AH, data={'javax.faces.partial.ajax': 'true', 'javax.faces.source': 'j_idt536', 'javax.faces.partial.execute': '@all', 'j_idt536': 'j_idt536', 'homepageformid': 'homepageformid', 'j_idt193_input': 'on', 'javax.faces.ViewState': vs}, timeout=20)
            m = re.search(r'<update id="j_id1:javax\.faces\.ViewState:0"><!\[CDATA\[(.*?)\]\]></update>', r.text)
            if m: vs = m.group(1)

            r = session.get(LI + '?faces-redirect=true', headers={**BASE, 'Referer': HP}, timeout=20)
            vs = re.search(r'<input[^>]*name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', r.text)
            if not vs:
                continue
            vs = vs.group(1)

            session.post(LI, headers={**BASE, 'Content-Type': 'application/x-www-form-urlencoded', 'Origin': 'https://vahan.parivahan.gov.in', 'Referer': LI + '?faces-redirect=true'}, data={'loginForm': 'loginForm', 'j_idt506': 'j_idt506', 'javax.faces.ViewState': vs, 'fitbalcTest': 'fitbalcTest', 'pur_cd': '86'}, timeout=20)
            r = session.get(FR, headers={**BASE, 'Referer': LI + '?faces-redirect=true'}, timeout=20)
            vs = re.search(r'<input[^>]*name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', r.text)
            if not vs:
                continue
            vs = vs.group(1)

            r = session.post(FR, headers={**AH, 'Referer': FR}, data={'javax.faces.partial.ajax': 'true', 'javax.faces.source': 'balanceFeesFine:validate_dtls', 'javax.faces.partial.execute': '@all', 'javax.faces.partial.render': 'balanceFeesFine:auth_panel', 'balanceFeesFine:validate_dtls': 'balanceFeesFine:validate_dtls', 'balanceFeesFine': 'balanceFeesFine', 'balanceFeesFine:tf_reg_no': rc, 'balanceFeesFine:tf_chasis_no': last5, 'javax.faces.ViewState': vs}, timeout=20)
            nums = re.findall(r'\b[6-9]\d{9}\b', r.text)
            if nums:
                return {'success': True, 'mobile': nums[0], 'chassis_last5': last5}
        except Exception:
            pass
        if attempt == 0:
            time.sleep(2)

    return {'success': False, 'mobile': 'Not Available', 'chassis_last5': last5}

# ----------------- UI / PAYMENT SCREENS -----------------
def send_payment_screen(chat_id):
    markup = types.InlineKeyboardMarkup()
    btn_upload = types.InlineKeyboardButton("📤 Send Payment Screenshot", callback_data="upload_proof")
    markup.add(btn_upload)

    caption = (
        "💳 *Recharge Search Credits:*\n\n"
        "• 1 Search = 5₹\n"
        "• 5 Searches = 25₹\n"
        "• 10 Searches = 50₹\n\n"
        f"💳 *UPI ID:* `{UPI_ID}`\n(Tap to copy)\n\n"
        "📌 *Steps:*\n"
        "1. Upar diye QR par payment karein.\n"
        "2. Payment ke baad neeche 'Send Payment Screenshot' dabayein."
    )
    try:
        bot.send_photo(chat_id, UPI_QR_PHOTO_URL, caption=caption, parse_mode="Markdown", reply_markup=markup)
    except Exception:
        bot.send_message(chat_id, f"{caption}\n\n🖼️ [View QR Code]({UPI_QR_PHOTO_URL})", parse_mode="Markdown", reply_markup=markup)

# ----------------- USER COMMANDS -----------------
@bot.message_handler(commands=['start'])
def start_msg(message):
    credits = get_user_credits(message.chat.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_recharge = types.InlineKeyboardButton("💳 Buy Credits (QR)", callback_data="buy_credits")
    btn_bal = types.InlineKeyboardButton(f"💰 Balance: {credits} Searches", callback_data="check_balance")
    markup.add(btn_recharge, btn_bal)

    welcome_text = (
        f"👋 *Welcome {message.from_user.first_name}*\n\n"
        "🚗 *Vehicle RC & Owner Number Finder Bot*\n\n"
        f"• *Current Balance:* `{credits}` Credits\n"
        "• *Charge:* 1 Search = 5₹ (1 Credit)\n\n"
        "👉 *Redeem Coupon:* `/redeem <code>`\n\n"
        "👇 _Gaadi ka RC number bhej kar search karein (e.g. DL01AB1234)_"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "buy_credits")
def buy_callback(call):
    send_payment_screen(call.message.chat.id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "check_balance")
def bal_callback(call):
    credits = get_user_credits(call.message.chat.id)
    bot.answer_callback_query(call.id, f"Aapka balance: {credits} Searches", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "upload_proof")
def ask_proof(call):
    waiting_screenshot.add(call.from_user.id)
    bot.send_message(call.message.chat.id, "Kripya transaction screenshot yahan send karein 👇")
    bot.answer_callback_query(call.id)

# ----------------- COUPON SYSTEM (CREATE & REDEEM) -----------------
@bot.message_handler(commands=['create'])
def create_coupon(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        points = int(message.text.split()[1])
        code = f"VC-{uuid.uuid4().hex[:6].upper()}"
        cursor.execute("INSERT INTO coupons (code, points, is_used) VALUES (?, ?, 0)", (code, points))
        conn.commit()
        bot.reply_to(
            message,
            f"✅ *Coupon Created Successfully!*\n\n"
            f"🎟️ *Code:* `{code}`\n"
            f"💰 *Credits:* `{points}`\n\n"
            f"User redemption format: `/redeem {code}`",
            parse_mode="Markdown"
        )
    except Exception:
        bot.reply_to(message, "⚠️ Usage: `/create <points>` (e.g., `/create 5`)", parse_mode="Markdown")

@bot.message_handler(commands=['redeem'])
def redeem_coupon(message):
    try:
        code = message.text.split()[1].upper()
        cursor.execute("SELECT points FROM coupons WHERE code = ? AND is_used = 0", (code,))
        row = cursor.fetchone()
        if row:
            points = row[0]
            new_bal = update_user_credits(message.chat.id, points)
            cursor.execute("UPDATE coupons SET is_used = 1 WHERE code = ?", (code,))
            conn.commit()
            bot.reply_to(
                message,
                f"🎉 *Redeemed Successfully!*\n\n+{points} Credits aapke account me add kar diye gaye hain.\n*Total Balance:* `{new_bal}` Credits.",
                parse_mode="Markdown"
            )
        else:
            bot.reply_to(message, "❌ Invalid ya pehle se use kiya gaya Coupon code.")
    except Exception:
        bot.reply_to(message, "⚠️ Usage: `/redeem <coupon_code>`", parse_mode="Markdown")

# ----------------- PAYMENT SCREENSHOT & APPROVAL -----------------
@bot.message_handler(content_types=['photo'])
def handle_proof_photo(message):
    user_id = message.chat.id
    if user_id in waiting_screenshot:
        waiting_screenshot.remove(user_id)

        admin_markup = types.InlineKeyboardMarkup(row_width=3)
        btn_1 = types.InlineKeyboardButton("+1 (₹5)", callback_data=f"add_1_{user_id}")
        btn_5 = types.InlineKeyboardButton("+5 (₹25)", callback_data=f"add_5_{user_id}")
        btn_10 = types.InlineKeyboardButton("+10 (₹50)", callback_data=f"add_10_{user_id}")
        btn_rej = types.InlineKeyboardButton("Reject ❌", callback_data=f"rej_pay_{user_id}")
        admin_markup.row(btn_1, btn_5, btn_10)
        admin_markup.add(btn_rej)

        user_info = f"@{message.from_user.username}" if message.from_user.username else "No Username"
        caption = f"🔔 *New Recharge Submission!*\nUser: {user_info}\nUser ID: `{user_id}`"

        file_id = message.photo[-1].file_id
        bot.send_photo(ADMIN_ID, file_id, caption=caption, parse_mode="Markdown", reply_markup=admin_markup)
        bot.reply_to(message, "⏳ Screenshot received! Admin verification ke baad balance add ho jayega.")
    else:
        bot.reply_to(message, "Pehle /start karke Buy Credits select karein.")

@bot.callback_query_handler(func=lambda call: call.data.startswith(("add_", "rej_pay_")))
def handle_admin_credit_approval(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Permission Denied!", show_alert=True)
        return

    parts = call.data.split("_")
    if parts[0] == "add":
        credits_to_add = int(parts[1])
        target_user = int(parts[2])
        new_total = update_user_credits(target_user, credits_to_add)

        try:
            bot.send_message(
                target_user,
                f"🎉 *Payment Approved!*\n\n+{credits_to_add} Search Credits aapke wallet me add ho gaye hain.\n*Total Balance:* {new_total} Credits.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

        try:
            bot.edit_message_caption(caption=call.message.caption + f"\n\nStatus: Approved (+{credits_to_add} Credits) ✅", chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception:
            pass

        bot.answer_callback_query(call.id, f"Added {credits_to_add} credits!")

    elif parts[0] == "rej":
        target_user = int(parts[2])
        try:
            bot.send_message(target_user, "❌ Aapka recharge payment reject kar diya gaya hai.")
        except Exception:
            pass

        try:
            bot.edit_message_caption(caption=call.message.caption + "\n\nStatus: Rejected ❌", chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception:
            pass

        bot.answer_callback_query(call.id, "Payment Rejected!")

# ----------------- BROADCAST COMMAND -----------------
@bot.message_handler(commands=['broadcast'])
def broadcast_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        bot.reply_to(message, "Usage: `/broadcast Aapka message`", parse_mode="Markdown")
        return

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    count = 0
    for (u_id,) in users:
        try:
            bot.send_message(u_id, text)
            count += 1
        except Exception:
            pass
    bot.reply_to(message, f"✅ Broadcast sent to {count} users!")

# ----------------- RC SEARCH HANDLER -----------------
@bot.message_handler(func=lambda msg: True)
def process_vehicle_search(message):
    user_id = message.chat.id
    credits = get_user_credits(user_id)

    raw = message.text.strip()
    rc = re.sub(r'[^A-Z0-9]', '', raw.upper())

    if len(rc) < 6 or len(rc) > 12:
        bot.reply_to(message, "⚠️ Sahi RC format bhejain (e.g. `DL01AB1234`).", parse_mode="Markdown")
        return

    if credits < 1:
        bot.reply_to(message, "❌ *Insufficient Balance!*\n\n1 Search karne ke liye ₹5 (1 Credit) zaroori hai.", parse_mode="Markdown")
        send_payment_screen(user_id)
        return

    load_msg = bot.reply_to(message, f"🔍 Searching details for `{rc}`... (-1 Credit)")

    last5, reg = get_vehicle_data(rc)
    if not last5:
        bot.edit_message_text(f"❌ RC `{rc}` nahi mili. Balance deduct nahi hua.", chat_id=message.chat.id, message_id=load_msg.message_id)
        return

    remaining = update_user_credits(user_id, -1)
    mob_res = get_mobile(rc, last5)

    mobile = mob_res.get('mobile', 'Not Available')
    last5_show = mob_res.get('chassis_last5', safe_get(reg, 'chassis')[-5:])

    res = (
        "🚗 *VEHICLE RC DETAILS*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👤 *OWNER DETAILS*\n"
        f"• *Owner Name:* {safe_get(reg, 'owner')}\n"
        f"• *Father Name:* {safe_get(reg, 'father')}\n"
        f"• *📱 Mobile No:* `{mobile}`\n"
        f"• *Status:* {safe_get(reg, 'status')}\n\n"
        "📋 *REGISTRATION*\n"
        f"• *RC Number:* `{safe_get(reg, 'reg_no')}`\n"
        f"• *Reg Date:* {safe_get(reg, 'reg_date')}\n"
        f"• *RTO Authority:* {safe_get(reg, 'reg_authority')}\n\n"
        "🚘 *SPECIFICATIONS*\n"
        f"• *Model:* {safe_get(reg, 'manufacturer')} {safe_get(reg, 'model')}\n"
        f"• *Fuel:* {safe_get(reg, 'fuel')}\n"
        f"• *Engine No:* `{safe_get(reg, 'engine')}`\n"
        f"• *Chassis No:* `***{last5_show}`\n\n"
        "🛡️ *INSURANCE*\n"
        f"• *Company:* {safe_get(reg, 'ins_company')}\n"
        f"• *Valid Till:* {safe_get(reg, 'ins_valid')}\n\n"
        "🏠 *ADDRESS*\n"
        f"• *Present:* {safe_get(reg, 'present_addr')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Remaining Balance:* `{remaining}` Credits"
    )

    bot.edit_message_text(res, chat_id=message.chat.id, message_id=load_msg.message_id, parse_mode="Markdown")

if __name__ == '__main__':
    bot.infinity_polling()
