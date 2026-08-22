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
VEHICLE_API = "https://vehicle-chass.vercel.app/api/vehicle?rc="

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
        print(f"QR Gen Error: {e}")
    return None, None

def send_auto_qr_screen(chat_id, message_id=None, amount=5):
    qr_url, order_id = generate_paytm_qr(chat_id, amount)
    if not qr_url:
        bot.send_message(chat_id, "❌ QR generate karne me samasya aayi. Kripya thodi der baad prayas karein.")
        return

    short_id = order_id[-6:] if len(order_id) >= 6 else order_id

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_paid = types.InlineKeyboardButton("✅ Paid", callback_data=f"checkpay_{order_id}")
    btn_new = types.InlineKeyboardButton("🔁 New QR", callback_data="gena_qr")
    markup.add(btn_paid, btn_new)

    caption = (
        f"💳 *Scan & Pay {amount}₹ on this QR Code*\n\n"
        "⚡ _Payment karne ke baad neeche '✅ Paid' button dabayein._\n"
        "Credits aapke wallet me automatically add ho jayenge!\n\n"
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

# ----------------- VEHICLE SCRAPER LOGIC -----------------
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

# ----------------- BOT COMMANDS -----------------
@bot.message_handler(commands=['start'])
def start_msg(message):
    credits = get_user_credits(message.chat.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_recharge = types.InlineKeyboardButton("💳 Auto Recharge (QR)", callback_data="gena_qr")
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

@bot.callback_query_handler(func=lambda call: call.data == "gena_qr")
def gena_qr_callback(call):
    bot.answer_callback_query(call.id, "Generating Dynamic QR...")
    send_auto_qr_screen(call.message.chat.id, message_id=call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "check_balance")
def bal_callback(call):
    credits = get_user_credits(call.message.chat.id)
    bot.answer_callback_query(call.id, f"Aapka balance: {credits} Searches", show_alert=True)

# ----------------- AUTO-PAYMENT VERIFICATION ENGINE -----------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("checkpay_"))
def auto_verify_payment(call):
    bot.answer_callback_query(call.id, "Checking payment status with Paytm...")
    order_id = call.data.split("_")[1]
    user_id = call.message.chat.id

    # Check if already processed
    cursor.execute("SELECT order_id FROM processed_orders WHERE order_id = ?", (order_id,))
    if cursor.fetchone():
        bot.answer_callback_query(call.id, "⚠️ This payment is already credited!", show_alert=True)
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

            # Record order to prevent reuse
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

            # Admin Notification
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
            bot.answer_callback_query(call.id, "❌ Payment not received yet!", show_alert=True)
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

    except Exception as e:
        bot.answer_callback_query(call.id, "⚠️ Error checking status. Try again.", show_alert=True)

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
        bot.reply_to(message, f"✅ *Coupon Created!*\n\n🎟️ Code: `{code}`\n💰 Points: {points}\n\nUse: `/redeem {code}`", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "Usage: `/create <points>`")

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
            bot.reply_to(message, f"🎉 *Redeemed Successfully!*\n\n+{points} Credits added.\n*Total Balance:* `{new_bal}` Credits.", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Invalid ya used Coupon code.")
    except Exception:
        bot.reply_to(message, "Usage: `/redeem <coupon_code>`")

# ----------------- BROADCAST COMMAND -----------------
@bot.message_handler(commands=['broadcast'])
def broadcast_command(message):
    if message.from_user.id != ADMIN_ID:
        return
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
        send_auto_qr_screen(user_id, amount=5)
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
