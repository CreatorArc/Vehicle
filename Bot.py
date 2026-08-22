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

# Nayi API Integration
VEHICLE_API = "https://vehicle-eight-vert.vercel.app/api?rc="

bot = telebot.TeleBot(BOT_TOKEN)
bot.remove_webhook()

# ----------------- DATABASE SETUP -----------------
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS coupons (code TEXT PRIMARY KEY, points INTEGER, is_used INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS processed_orders (order_id TEXT PRIMARY KEY, user_id INTEGER, amount REAL, points INTEGER, created_at TEXT)")
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

# ----------------- QR SYSTEM -----------------
def send_auto_qr_screen(chat_id, message_id=None, amount=5):
    try:
        url = f"{QR_API_URL}/?id={PAYTM_MID}&upi={PAYTM_UPI}&amount={amount}"
        response = requests.post(url, timeout=15)
        data = response.json()
        qr_url = data.get('qrImageUrl')
        order_id = data.get('trackId')
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("✅ Paid", callback_data=f"checkpay_{order_id}"))

        if message_id:
            bot.edit_message_media(chat_id=chat_id, message_id=message_id, media=types.InputMediaPhoto(media=qr_url, caption=f"Scan & Pay {amount}₹ for {amount//5} Credit(s)", parse_mode="Markdown"), reply_markup=markup)
        else:
            bot.send_photo(chat_id, qr_url, caption=f"Scan & Pay {amount}₹ for {amount//5} Credit(s)", reply_markup=markup)
    except Exception:
        bot.send_message(chat_id, "❌ Error generating QR. Try again.")

# ----------------- VEHICLE & MOBILE SCRAPER -----------------
def safe_get(d, keys, default='N/A'):
    for key in keys:
        if d.get(key): return str(d.get(key))
    return default

def get_vehicle_data(rc):
    try:
        response = requests.get(VEHICLE_API + rc, timeout=20)
        data = response.json()
        if not data or 'error' in data: return None, None
        
        reg = {
            'owner': safe_get(data, ['owner_name', 'OwnerName', 'owner']),
            'father': safe_get(data, ['father_name', 'FatherName', 'father']),
            'model': safe_get(data, ['model', 'maker_model', 'Model']),
            'engine': safe_get(data, ['engine', 'engine_no', 'EngineNumber']),
            'chassis': safe_get(data, ['chassis', 'chassis_no', 'ChassisNumber']),
            'ins_comp': safe_get(data, ['insurance_company', 'InsuranceCompany', 'insurance']),
            'ins_valid': safe_get(data, ['insurance_valid_till', 'InsuranceValidTill']),
            'address': safe_get(data, ['address', 'PresentAddress', 'present_address'])
        }
        return reg['chassis'][-5:], reg
    except Exception: return None, None

def get_mobile(rc, last5):
    # (Parivahan scraper logic yahi rahega jo pehle tha, short code)
    # Note: Scraper logic is complex, keep the one that was working in your Termux
    return {'success': True, 'mobile': '9876543210', 'chassis_last5': last5}

# ----------------- HANDLERS -----------------
@bot.message_handler(commands=['start'])
def start_msg(message):
    bot.reply_to(message, "🚗 *RC Bot Active*\nSend RC Number to search.", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("checkpay_"))
def auto_verify_payment(call):
    order_id = call.data.split("_")[1]
    url = f"{VERIFY_API_URL}/?id={PAYTM_MID}&trn={order_id}"
    data = requests.post(url).json()
    if data.get("STATUS") == "TXN_SUCCESS":
        update_user_credits(call.message.chat.id, 1)
        bot.edit_message_caption("✅ Payment Success! 1 Credit added.", chat_id=call.message.chat.id, message_id=call.message.message_id)

@bot.message_handler(func=lambda msg: True)
def process_vehicle_search(message):
    if message.text.startswith('/'): return
    rc = re.sub(r'[^A-Z0-9]', '', message.text.strip().upper())
    if len(rc) < 6: return
    
    if get_user_credits(message.chat.id) < 1:
        send_auto_qr_screen(message.chat.id, amount=5)
        return

    load_msg = bot.reply_to(message, "🔍 Searching...")
    last5, reg = get_vehicle_data(rc)
    
    if not reg:
        bot.edit_message_text("❌ Record nahi mila.", message.chat.id, load_msg.message_id)
        return

    update_user_credits(message.chat.id, -1)
    res = f"🚗 *RC:* {rc}\n👤 *Owner:* {reg['owner']}\n🏗️ *Chassis:* {reg['chassis']}\n🏠 *Address:* {reg['address']}"
    bot.edit_message_text(res, message.chat.id, load_msg.message_id, parse_mode="Markdown")

if __name__ == '__main__':
    bot.infinity_polling()
