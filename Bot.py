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

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)
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
        response = requests.post(url, timeout=7)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                return data.get('qrImageUrl'), data.get('trackId')
    except Exception:
        pass
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
        f"💳 <b>Recharge Search Credits:</b>\n\n"
        f"• 1 Search = ₹5\n"
        f"• <b>Amount:</b> ₹{amount}\n\n"
        "⚡ <i>Payment karne ke baad neeche '✅ Paid' dabayein.</i>\n"
        f"🆔 <b>Order ID:</b> <code>...{short_id}</code>"
    )

    if message_id:
        try:
            bot.edit_message_media(
                chat_id=chat_id,
                message_id=message_id,
                media=types.InputMediaPhoto(media=qr_url, caption=caption, parse_mode="HTML"),
                reply_markup=markup
            )
            return
        except Exception:
            pass

    bot.send_photo(chat_id, qr_url, caption=caption, parse_mode="HTML", reply_markup=markup)

# ----------------- VEHICLE DATA FETCHER (ROBUST) -----------------
def safe_str(val, default='N/A'):
    if val in [None, '', 'null', 'None', 'N/A']:
        return default
    return str(val).strip()

def get_vehicle_data(rc):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(VEHICLE_API + rc, headers=headers, timeout=6)
        if response.status_code != 200:
            return None
            
        data = response.json()
        if not data or not isinstance(data, dict) or data.get('error'):
            return None

        v = data.get('vehicle', {}) if isinstance(data.get('vehicle'), dict) else {}
        s = data.get('specifications', {}) if isinstance(data.get('specifications'), dict) else {}
        ins = data.get('insurance', {}) if isinstance(data.get('insurance'), dict) else {}
        addr = data.get('address', {}) if isinstance(data.get('address'), dict) else {}

        owner = data.get('owner_name') or data.get('OwnerName') or data.get('owner') or v.get('Owner') or v.get('owner_name')
        father = data.get('father_name') or data.get('FatherName') or data.get('father') or v.get('Father Name')
        reg_no = data.get('reg_no') or data.get('RegistrationNumber') or data.get('rc_number') or v.get('Registration Number') or rc
        reg_date = data.get('reg_date') or data.get('RegistrationDate') or data.get('registration_date') or v.get('Registration Date')
        rto = data.get('rto') or data.get('RegistrationAuthority') or data.get('reg_authority') or v.get('Registration Authority')
        model = data.get('maker_model') or data.get('model') or data.get('Model') or f"{s.get('Manufacturer', '')} {s.get('Model', '')}".strip()
        fuel = data.get('fuel_type') or data.get('fuel') or data.get('FuelType') or s.get('Fuel Type')
        engine = data.get('engine_no') or data.get('EngineNumber') or data.get('engine') or s.get('Engine Number')
        chassis = data.get('chassis_no') or data.get('ChassisNumber') or data.get('chassis') or s.get('Chassis Number')
        ins_comp = data.get('insurance_company') or data.get('InsuranceCompany') or data.get('insurance') or ins.get('Company')
        ins_valid = data.get('insurance_valid_till') or data.get('InsuranceValidTill') or data.get('insurance_expiry') or ins.get('Valid Till')
        present_addr = data.get('address') or data.get('PresentAddress') or data.get('present_address') or data.get('permanent_address') or addr.get('Present Address')
        mobile = data.get('mobile') or data.get('mobile_no') or data.get('phone') or 'Not Available'
        status = data.get('status') or data.get('Status') or data.get('rc_status') or v.get('Status') or 'ACTIVE'

        return {
            'owner': safe_str(owner),
            'father': safe_str(father),
            'reg_no': safe_str(reg_no),
            'reg_date': safe_str(reg_date),
            'rto': safe_str(rto),
            'model': safe_str(model),
            'fuel': safe_str(fuel),
            'engine': safe_str(engine),
            'chassis': safe_str(chassis),
            'ins_company': safe_str(ins_comp),
            'ins_valid': safe_str(ins_valid),
            'present_addr': safe_str(present_addr),
            'mobile': safe_str(mobile),
            'status': safe_str(status)
        }
    except Exception:
        return None

# ----------------- BOT COMMANDS & UI -----------------
@bot.message_handler(commands=['start'])
def start_msg(message):
    name = message.from_user.first_name or "User"
    credits = get_user_credits(message.chat.id)

    welcome_text = (
        f"👋 <b>Welcome {name}</b>\n\n"
        "🚗 <b>Vehicle RC & Owner Number Finder Bot</b>\n\n"
        f"• <b>Current Balance:</b> {credits} Credits\n"
        "• <b>Charge:</b> 1 Search = 5₹ (1 Credit)\n\n"
        "👉 <b>Redeem Coupon:</b> <code>/redeem &lt;code&gt;</code>\n\n"
        "👇 <i>Gaadi ka RC number bhej kar search karein (e.g. DL01AB1234)</i>"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="HTML", reply_markup=get_main_menu(message.chat.id))

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
        response = requests.post(url, timeout=7)
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
                "🎉 <b>Deposit Completed Successfully!</b>\n\n"
                f"💵 <b>Amount Paid:</b> {amount} INR\n"
                f"⚡ <b>Credits Gained:</b> +{points_gained} Searches\n"
                f"💰 <b>Total Wallet Balance:</b> <code>{new_bal}</code> Credits\n\n"
                f"🆔 <b>Order ID:</b> <code>{order_id}</code>\n\n"
                "👉 <i>Ab aap gaadi ka RC number bhej kar turant search kar sakte hain!</i>"
            )
            bot.edit_message_caption(
                caption=success_caption,
                chat_id=user_id,
                message_id=call.message.message_id,
                parse_mode="HTML"
            )

            bot.send_message(
                ADMIN_ID,
                f"🔔 <b>New Auto-Payment Received!</b>\n\n👤 User: <code>{user_id}</code>\n💰 Amount: ₹{amount}\n⚡ Credits: +{points_gained}\n🆔 Order ID: <code>{order_id}</code>",
                parse_mode="HTML"
            )
        else:
            bot.answer_callback_query(call.id, "❌ Payment nahi mili abhi tak!", show_alert=True)
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
        bot.reply_to(message, f"✅ <b>Coupon Created Successfully!</b>\n\n🎟️ Code: <code>{code}</code>\n💰 Points: {points}\n\nUse: <code>/redeem {code}</code>", parse_mode="HTML")
    except Exception:
        bot.reply_to(message, "Usage: <code>/create &lt;points&gt;</code>", parse_mode="HTML")

@bot.message_handler(commands=['addcredits'])
def admin_add_direct(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split()
        target_uid = int(parts[1])
        pts = int(parts[2])
        new_bal = update_user_credits(target_uid, pts)
        bot.reply_to(message, f"✅ User <code>{target_uid}</code> ko {pts} credits diye. Total: <code>{new_bal}</code>", parse_mode="HTML")
    except Exception:
        bot.reply_to(message, "Usage: <code>/addcredits &lt;user_id&gt; &lt;amount&gt;</code>", parse_mode="HTML")

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
            bot.reply_to(message, f"🎉 <b>Redeemed Successfully!</b>\n\n+{points} Credits added.\n<b>Total Balance:</b> <code>{new_bal}</code> Credits.", parse_mode="HTML", reply_markup=get_main_menu(message.chat.id))
        else:
            bot.reply_to(message, "❌ Invalid ya used Coupon code.")
    except Exception:
        bot.reply_to(message, "Usage: <code>/redeem &lt;coupon_code&gt;</code>", parse_mode="HTML")

@bot.message_handler(commands=['broadcast'])
def broadcast_command(message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        bot.reply_to(message, "Usage: <code>/broadcast Aapka message</code>", parse_mode="HTML")
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
        bot.reply_to(message, "⚠️ Sahi RC format bhejein (e.g. <code>DL01AB1234</code>).", parse_mode="HTML")
        return

    if credits < 1:
        bot.reply_to(message, "❌ <b>Insufficient Balance!</b>\n\n1 Search karne ke liye ₹5 (1 Credit) zaroori hai.", parse_mode="HTML")
        send_auto_qr_screen(user_id, amount=5)
        return

    load_msg = bot.reply_to(message, f"🔍 Searching details for <code>{rc}</code>... (-1 Credit)", parse_mode="HTML")
    
    try:
        reg = get_vehicle_data(rc)
        if not reg:
            bot.edit_message_text(f"❌ RC <code>{rc}</code> records nahi mile. Balance deduct nahi hua.", chat_id=user_id, message_id=load_msg.message_id, parse_mode="HTML")
            return

        remaining = update_user_credits(user_id, -1)

        res = (
            "🚗 <b>VEHICLE RC DETAILS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👤 <b>OWNER DETAILS</b>\n"
            f"• <b>Owner Name:</b> {reg['owner']}\n"
            f"• <b>Father Name:</b> {reg['father']}\n"
            f"• 📱 <b>Mobile No:</b> <code>{reg['mobile']}</code>\n"
            f"• <b>Status:</b> {reg['status']}\n\n"
            "📋 <b>REGISTRATION</b>\n"
            f"• <b>RC Number:</b> {reg['reg_no']}\n"
            f"• <b>Reg Date:</b> {reg['reg_date']}\n"
            f"• <b>RTO Authority:</b> {reg['rto']}\n\n"
            "🚘 <b>SPECIFICATIONS</b>\n"
            f"• <b>Model:</b> {reg['model']}\n"
            f"• <b>Fuel:</b> {reg['fuel']}\n"
            f"• <b>Engine No:</b> <code>{reg['engine']}</code>\n"
            f"• <b>Chassis No:</b> <code>{reg['chassis']}</code>\n\n"
            "🛡️ <b>INSURANCE</b>\n"
            f"• <b>Company:</b> {reg['ins_company']}\n"
            f"• <b>Valid Till:</b> {reg['ins_valid']}\n\n"
            "🏠 <b>ADDRESS</b>\n"
            f"• <b>Present:</b> {reg['present_addr']}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Remaining Balance:</b> {remaining} Credits"
        )

        bot.edit_message_text(res, chat_id=user_id, message_id=load_msg.message_id, parse_mode="HTML", reply_markup=get_main_menu(user_id))
    except Exception as e:
        bot.edit_message_text(f"❌ Error aayi details process karne me.", chat_id=user_id, message_id=load_msg.message_id)

if __name__ == '__main__':
    bot.infinity_polling()
