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

# ----------------- FLASK KEEP-ALIVE SERVER -----------------
app = Flask('')

@app.route('/')
def home():
    return "Vehicle RC Auto-Payment Bot is running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask).start()

# ----------------- CONFIGURATION -----------------
BOT_TOKEN = "8834683428:AAGlWn91Xj4UjCu6pEVyuLoSWaU_SLjmS00"
ADMIN_ID = 8800158361

PAYTM_MID = "FdGQlV45296340803916"
PAYTM_UPI = "paytmqr2810050501011gv6cueh16my@paytm"

QR_API_URL = "https://paytms.aimbotaxe4.workers.dev"
VERIFY_API_URL = "https://paytmv.aimbotaxe4.workers.dev"
VEHICLE_API = "https://vehicle-eight-vert.vercel.app/api?rc="

bot = telebot.TeleBot(BOT_TOKEN)
bot.remove_webhook()

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

cursor.execute("""
    CREATE TABLE IF NOT EXISTS processed_orders (
        order_id TEXT PRIMARY KEY,
        user_id INTEGER,
        amount REAL,
        points INTEGER,
        created_at TEXT
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

def get_main_menu(uid):
    credits = get_user_credits(uid)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💳 Buy Credits (QR)", f"💰 Balance: {credits} Searches")
    return markup

# ----------------- AUTO QR GENERATION -----------------
def generate_paytm_qr(user_id, amount=5):
    try:
        url = f"{QR_API_URL}/?id={PAYTM_MID}&upi={PAYTM_UPI}&amount={amount}"
        response = requests.post(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                return data.get('qrImageUrl'), data.get('trackId')
    except Exception as e:
        print(f"QR Error: {e}")
    return None, None

def send_auto_qr_screen(chat_id, message_id=None, amount=5):
    qr_url, order_id = generate_paytm_qr(chat_id, amount)
    if not qr_url:
        bot.send_message(chat_id, "❌ QR generate karne me problem aayi. Kripya dobara try karein.")
        return

    short_id = order_id[-6:] if len(order_id) >= 6 else order_id

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_paid = types.InlineKeyboardButton("✅ Paid", callback_data=f"checkpay_{order_id}")
    btn_new = types.InlineKeyboardButton("🔁 New QR", callback_data="gena_qr")
    markup.add(btn_paid, btn_new)

    caption = (
        f"💳 *Scan & Pay {amount}₹ on this QR Code*\n\n"
        "⚡ _Payment karne ke baad neeche '✅ Paid' dabayein._\n"
        "Credits wallet me add ho jayenge!\n\n"
        f"🆔 *Order ID:* `...{short_id}`\n"
        f"💰 *Rate:* 5₹ = 1 Search Credit"
    )

    if message_id:
        try:
            bot.edit_message_media(
                chat_id=chat_id,
                message_id=message_id,
                media=types.InputMediaPhoto(media=qr_url, caption=caption, parse_mode="Markdown"),
                reply_markup=markup
            )
            return
        except Exception:
            pass

    bot.send_photo(chat_id, qr_url, caption=caption, parse_mode="Markdown", reply_markup=markup)

# ----------------- PARIVAHAN LIVE MOBILE SCRAPER -----------------
def get_mobile(rc, last5):
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
        'Connection': 'keep-alive'
    }
    session.headers.update(headers)

    HP = 'https://vahan.parivahan.gov.in/vahanservice/vahan/ui/statevalidation/homepage.xhtml?statecd=Mzc2MzM2MzAzNjY0MzIzODM3NjIzNjY0MzY2MjM3NDQ0Yw=='
    HB = 'https://vahan.parivahan.gov.in/vahanservice/vahan/ui/statevalidation/homepage.xhtml'
    LI = 'https://vahan.parivahan.gov.in/vahanservice/vahan/ui/usermgmt/login.xhtml'
    FR = 'https://vahan.parivahan.gov.in/vahanservice/vahan/ui/balanceservice/form_reschedule_fitness.xhtml'

    for _ in range(2):
        try:
            r = session.get(HP, timeout=15)
            vs = re.search(r'<input[^>]*name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', r.text)
            if not vs: continue
            vs = vs.group(1)

            cid = 'j_idt193'
            cm = re.search(r'<div[^>]*id="(j_idt\d+)"[^>]*class="[^"]*ui-chkbox', r.text)
            if cm: cid = cm.group(1)

            AH = {
                'Accept': 'application/xml, text/xml, */*; q=0.01',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Faces-Request': 'partial/ajax',
                'X-Requested-With': 'XMLHttpRequest',
                'Origin': 'https://vahan.parivahan.gov.in',
                'Referer': HP
            }

            r = session.post(HB, headers=AH, data={
                'javax.faces.partial.ajax': 'true',
                'javax.faces.source': 'fit_c_office_to',
                'javax.faces.partial.execute': 'fit_c_office_to',
                'javax.faces.behavior.event': 'change',
                'homepageformid': 'homepageformid',
                'fit_c_office_to_input': '1',
                'javax.faces.ViewState': vs
            }, timeout=15)
            m = re.search(r'<update id="j_id1:javax\.faces\.ViewState:0"><!\[CDATA\[(.*?)\]\]></update>', r.text)
            if m: vs = m.group(1)

            r = session.post(HB, headers=AH, data={
                'javax.faces.partial.ajax': 'true',
                'javax.faces.source': cid,
                'javax.faces.partial.execute': cid,
                'javax.faces.partial.render': 'proccedHomeButtonId',
                'javax.faces.behavior.event': 'change',
                'homepageformid': 'homepageformid',
                f'{cid}_input': 'on',
                'javax.faces.ViewState': vs
            }, timeout=15)
            m = re.search(r'<update id="j_id1:javax\.faces\.ViewState:0"><!\[CDATA\[(.*?)\]\]></update>', r.text)
            if m: vs = m.group(1)

            r = session.post(HB, headers=AH, data={
                'javax.faces.partial.ajax': 'true',
                'javax.faces.source': 'proccedHomeButtonId',
                'javax.faces.partial.execute': '@all',
                'proccedHomeButtonId': 'proccedHomeButtonId',
                'homepageformid': 'homepageformid',
                f'{cid}_input': 'on',
                'javax.faces.ViewState': vs
            }, timeout=15)
            m = re.search(r'<update id="j_id1:javax\.faces\.ViewState:0"><!\[CDATA\[(.*?)\]\]></update>', r.text)
            if m: vs = m.group(1)

            dlg = 'j_idt536'
            dm = re.search(r'id="(j_idt\d+)"[^>]*class="[^"]*ui-button', r.text)
            if dm: dlg = dm.group(1)

            r = session.post(HB, headers=AH, data={
                'javax.faces.partial.ajax': 'true',
                'javax.faces.source': dlg,
                'javax.faces.partial.execute': '@all',
                dlg: dlg,
                'homepageformid': 'homepageformid',
                f'{cid}_input': 'on',
                'javax.faces.ViewState': vs
            }, timeout=15)
            m = re.search(r'<update id="j_id1:javax\.faces\.ViewState:0"><!\[CDATA\[(.*?)\]\]></update>', r.text)
            if m: vs = m.group(1)

            r = session.get(LI + '?faces-redirect=true', headers={**headers, 'Referer': HP}, timeout=15)
            vs = re.search(r'<input[^>]*name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', r.text)
            if not vs: continue
            vs = vs.group(1)

            fit = 'j_idt506'
            fm = re.search(r'id="(j_idt\d+)"[^>]*type="submit"', r.text)
            if fit and fm: fit = fm.group(1)

            session.post(LI, headers={
                **headers,
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://vahan.parivahan.gov.in',
                'Referer': LI + '?faces-redirect=true'
            }, data={
                'loginForm': 'loginForm',
                fit: fit,
                'javax.faces.ViewState': vs,
                'fitbalcTest': 'fitbalcTest',
                'pur_cd': '86'
            }, timeout=15)

            r = session.get(FR, headers={**headers, 'Referer': LI + '?faces-redirect=true'}, timeout=15)
            vs = re.search(r'<input[^>]*name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', r.text)
            if not vs: continue
            vs = vs.group(1)

            r = session.post(FR, headers={**AH, 'Referer': FR}, data={
                'javax.faces.partial.ajax': 'true',
                'javax.faces.source': 'balanceFeesFine:validate_dtls',
                'javax.faces.partial.execute': '@all',
                'javax.faces.partial.render': 'balanceFeesFine:auth_panel',
                'balanceFeesFine:validate_dtls': 'balanceFeesFine:validate_dtls',
                'balanceFeesFine': 'balanceFeesFine',
                'balanceFeesFine:tf_reg_no': rc,
                'balanceFeesFine:tf_chasis_no': last5,
                'javax.faces.ViewState': vs
            }, timeout=15)

            patterns = [
                r'id="balanceFeesFine:tf_mobile"[^>]*value="(\d{10})"',
                r'value="(\d{10})"[^>]*id="balanceFeesFine:tf_mobile"',
                r'tf_mobile[^>]*value="(\d{10})"'
            ]
            for p in patterns:
                mo = re.search(p, r.text)
                if mo and mo.group(1)[0] in '6789':
                    return mo.group(1)

            nums = re.findall(r'\b[6-9]\d{9}\b', r.text)
            if nums: return nums[0]
        except Exception:
            pass
        time.sleep(1)

    return 'Not Available'

# ----------------- VEHICLE DATA FETCHER -----------------
def safe_get(d, keys, default='N/A'):
    for key in keys:
        val = d.get(key)
        if val not in [None, '', 'N/A', 'null']:
            return str(val).strip()
    return default

def get_vehicle_data(rc):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(VEHICLE_API + rc, headers=headers, timeout=20)
        data = response.json()
        if not data or data.get('error'):
            return None

        # Nested format support
        v = data.get('vehicle', {}) if isinstance(data.get('vehicle'), dict) else {}
        s = data.get('specifications', {}) if isinstance(data.get('specifications'), dict) else {}
        ins = data.get('insurance', {}) if isinstance(data.get('insurance'), dict) else {}
        addr = data.get('address', {}) if isinstance(data.get('address'), dict) else {}

        chassis = safe_get(data, ['chassis_no', 'ChassisNumber', 'chassis'], safe_get(s, ['Chassis Number', 'chassis_no'], ''))

        reg = {
            'reg_no': safe_get(data, ['reg_no', 'RegistrationNumber', 'rc_number'], safe_get(v, ['Registration Number'], rc)),
            'owner': safe_get(data, ['owner_name', 'OwnerName', 'owner'], safe_get(v, ['Owner', 'owner_name'])),
            'father': safe_get(data, ['father_name', 'FatherName', 'father'], safe_get(v, ['Father Name', 'father_name'])),
            'status': safe_get(data, ['status', 'Status', 'rc_status'], safe_get(v, ['Status'], 'ACTIVE')),
            'reg_authority': safe_get(data, ['rto', 'RegistrationAuthority', 'reg_authority'], safe_get(v, ['Registration Authority'])),
            'reg_date': safe_get(data, ['reg_date', 'RegistrationDate', 'registration_date'], safe_get(v, ['Registration Date'])),
            'model': safe_get(data, ['maker_model', 'model', 'Model', 'vehicle_model'], f"{safe_get(s, ['Manufacturer'], '')} {safe_get(s, ['Model'], '')}".strip()),
            'fuel': safe_get(data, ['fuel_type', 'fuel', 'FuelType'], safe_get(s, ['Fuel Type', 'fuel_type'])),
            'engine': safe_get(data, ['engine_no', 'EngineNumber', 'engine'], safe_get(s, ['Engine Number', 'engine_no'])),
            'chassis': chassis if chassis else 'N/A',
            'ins_company': safe_get(data, ['insurance_company', 'InsuranceCompany', 'insurance'], safe_get(ins, ['Company', 'insurance_company'])),
            'ins_valid': safe_get(data, ['insurance_valid_till', 'InsuranceValidTill', 'insurance_expiry'], safe_get(ins, ['Valid Till', 'insurance_valid_till'])),
            'present_addr': safe_get(data, ['address', 'PresentAddress', 'present_address', 'permanent_address'], safe_get(addr, ['Present Address', 'address']))
        }
        return reg
    except Exception:
        return None

# ----------------- BOT COMMANDS & UI -----------------
@bot.message_handler(commands=['start'])
def start_msg(message):
    name = message.from_user.first_name or "User"
    credits = get_user_credits(message.chat.id)

    welcome_text = (
        f"👋 *Welcome {name}*\n\n"
        "🚗 *Vehicle RC & Owner Number Finder Bot*\n\n"
        f"• *Current Balance:* {credits} Credits\n"
        "• *Charge:* 1 Search = 5₹ (1 Credit)\n\n"
        "👉 *Redeem Coupon:* `/redeem <code>`\n\n"
        "👇 _Gaadi ka RC number bhej kar search karein (e.g. DL01AB1234)_"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_main_menu(message.chat.id))

@bot.callback_query_handler(func=lambda call: call.data == "gena_qr")
def gena_qr_callback(call):
    bot.answer_callback_query(call.id, "Generating Dynamic QR...")
    send_auto_qr_screen(call.message.chat.id, message_id=call.message.message_id)

# ----------------- PAYMENT VERIFICATION ENGINE -----------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("checkpay_"))
def auto_verify_payment(call):
    bot.answer_callback_query(call.id, "Checking payment status...")
    order_id = call.data.split("_")[1]
    user_id = call.message.chat.id

    cursor.execute("SELECT order_id FROM processed_orders WHERE order_id = ?", (order_id,))
    if cursor.fetchone():
        bot.answer_callback_query(call.id, "⚠️ Yeh payment pehle hi credit ho chuki hai!", show_alert=True)
        return

    try:
        url = f"{VERIFY_API_URL}/?id={PAYTM_MID}&trn={order_id}"
        response = requests.post(url, timeout=20)
        data = response.json()

        stat = data.get("STATUS", "")
        resp = data.get("RESPMSG", "")
        try:
            amount = float(data.get("TXNAMOUNT", 0) or 0)
        except Exception:
            amount = 0.0

        if stat == "TXN_SUCCESS" and resp == "Txn Success" and amount >= 5:
            points_gained = int(amount // 5)
            new_bal = update_user_credits(user_id, points_gained)

            cursor.execute("INSERT INTO processed_orders (order_id, user_id, amount, points, created_at) VALUES (?, ?, ?, ?, ?)", 
                           (order_id, user_id, amount, points_gained, time.strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()

            success_caption = (
                "🎉 *Deposit Completed Successfully!*\n\n"
                f"💵 *Amount Paid:* {amount} INR\n"
                f"⚡ *Credits Gained:* +{points_gained} Searches\n"
                f"💰 *Total Wallet Balance:* `{new_bal}` Credits\n\n"
                f"🆔 *Order ID:* `{order_id}`\n\n"
                "👉 _Ab aap gaadi ka RC number bhej kar turant search kar sakte hain!_"
            )
            bot.edit_message_caption(
                caption=success_caption,
                chat_id=user_id,
                message_id=call.message.message_id,
                parse_mode="Markdown"
            )

            bot.send_message(
                ADMIN_ID,
                f"🔔 *New Auto-Payment Received!*\n\n"
                f"👤 User: `{user_id}`\n"
                f"💰 Amount: ₹{amount}\n"
                f"⚡ Credits: +{points_gained}\n"
                f"🆔 Order ID: `{order_id}`",
                parse_mode="Markdown"
            )
        else:
            bot.answer_callback_query(call.id, "❌ Payment nahi mili abhi tak!", show_alert=True)
            failed_markup = types.InlineKeyboardMarkup(row_width=2)
            failed_markup.add(
                types.InlineKeyboardButton("🔄 Check Again", callback_data=f"checkpay_{order_id}"),
                types.InlineKeyboardButton("🔁 New QR", callback_data="gena_qr")
            )
            try:
                bot.edit_message_caption(
                    caption=f"❌ *Payment Not Found Yet*\n\nAgar aapne pay kar diya hai toh 5-10 second baad 'Check Again' dabayein.\n\n🆔 Order ID: `{order_id}`",
                    chat_id=user_id,
                    message_id=call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=failed_markup
                )
            except Exception:
                pass
    except Exception:
        bot.answer_callback_query(call.id, "⚠️ Verification error. Dobara try karein.", show_alert=True)

# ----------------- ADMIN COMMANDS -----------------
@bot.message_handler(commands=['create'])
def create_coupon(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        points = int(message.text.split()[1])
        code = f"VC-{uuid.uuid4().hex[:6].upper()}"
        cursor.execute("INSERT INTO coupons (code, points, is_used) VALUES (?, ?, 0)", (code, points))
        conn.commit()
        bot.reply_to(message, f"✅ *Coupon Created Successfully!*\n\n🎟️ Code: `{code}`\n💰 Points: {points}\n\nUse: `/redeem {code}`", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "Usage: `/create <points>`")

@bot.message_handler(commands=['addcredits'])
def admin_add_direct(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split()
        target_uid = int(parts[1])
        pts = int(parts[2])
        new_bal = update_user_credits(target_uid, pts)
        bot.reply_to(message, f"✅ User `{target_uid}` ko {pts} credits diye. Total: `{new_bal}`")
    except Exception:
        bot.reply_to(message, "Usage: `/addcredits <user_id> <amount>`")

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
            bot.reply_to(message, f"🎉 *Redeemed Successfully!*\n\n+{points} Credits added.\n*Total Balance:* `{new_bal}` Credits.", parse_mode="Markdown", reply_markup=get_main_menu(message.chat.id))
        else:
            bot.reply_to(message, "❌ Invalid ya used Coupon code.")
    except Exception:
        bot.reply_to(message, "Usage: `/redeem <coupon_code>`")

@bot.message_handler(commands=['broadcast'])
def broadcast_command(message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        bot.reply_to(message, "Usage: `/broadcast Aapka message`")
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

# ----------------- RC SEARCH & MENU HANDLER -----------------
@bot.message_handler(func=lambda msg: True)
def process_vehicle_search(message):
    text = message.text.strip()
    user_id = message.chat.id
    credits = get_user_credits(user_id)

    if text == "💳 Buy Credits (QR)":
        send_auto_qr_screen(user_id, amount=5)
        return

    if text.startswith("💰 Balance"):
        bot.reply_to(message, f"Aapka balance: {credits} Searches hai.", reply_markup=get_main_menu(user_id))
        return

    if text.startswith('/'): return

    rc = re.sub(r'[^A-Z0-9]', '', text.upper())
    if len(rc) < 6 or len(rc) > 12:
        bot.reply_to(message, "⚠️ Sahi RC format bhejein (e.g. `DL01AB1234`).", parse_mode="Markdown")
        return

    if credits < 1:
        bot.reply_to(message, "❌ *Insufficient Balance!*\n\n1 Search karne ke liye ₹5 (1 Credit) zaroori hai.", parse_mode="Markdown")
        send_auto_qr_screen(user_id, amount=5)
        return

    load_msg = bot.reply_to(message, f"🔍 Searching details for `{rc}`... (-1 Credit)")
    reg = get_vehicle_data(rc)

    if not reg:
        bot.edit_message_text(f"❌ RC `{rc}` records nahi mile. Balance deduct nahi hua.", chat_id=user_id, message_id=load_msg.message_id)
        return

    chassis_full = reg['chassis']
    last5 = chassis_full[-5:] if len(chassis_full) >= 5 else "00000"
    mobile_num = get_mobile(rc, last5)

    remaining = update_user_credits(user_id, -1)

    res = (
        "🚗 *VEHICLE RC DETAILS*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👤 *OWNER DETAILS*\n"
        f"• *Owner Name:* {reg['owner']}\n"
        f"• *Father Name:* {reg['father']}\n"
        f"• 📱 *Mobile No:* `{mobile_num}`\n"
        f"• *Status:* {reg['status']}\n\n"
        "📋 *REGISTRATION*\n"
        f"• *RC Number:* {reg['reg_no']}\n"
        f"• *Reg Date:* {reg['reg_date']}\n"
        f"• *RTO Authority:* {reg['reg_authority']}\n\n"
        "🚘 *SPECIFICATIONS*\n"
        f"• *Model:* {reg['model']}\n"
        f"• *Fuel:* {reg['fuel']}\n"
        f"• *Engine No:* {reg['engine']}\n"
        f"• *Chassis No:* `{chassis_full}`\n\n"
        "🛡️ *INSURANCE*\n"
        f"• *Company:* {reg['ins_company']}\n"
        f"• *Valid Till:* {reg['ins_valid']}\n\n"
        "🏠 *ADDRESS*\n"
        f"• *Present:* {reg['present_addr']}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Remaining Balance:* {remaining} Credits"
    )

    bot.edit_message_text(res, chat_id=user_id, message_id=load_msg.message_id, parse_mode="Markdown", reply_markup=get_main_menu(user_id))

if __name__ == '__main__':
    bot.infinity_polling()
