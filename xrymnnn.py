import sqlite3
import time
import threading
import random
import telebot
from telebot import types

# ==================== ТОКЕН ====================
TOKEN_PART1 = "9243031085:"
TOKEN_PART2 = "AAGUHe0IInjMteEspHJYHX3WWpAFsHyT44A"
bot = telebot.TeleBot(TOKEN_PART1 + TOKEN_PART2)

# ==================== БАЗА ====================
# timeout=30 нужен, чтобы база ждала, если занята другим потоком, а не падала
conn = sqlite3.connect("hamster.db", check_same_thread=False, timeout=30)

conn.execute("""CREATE TABLE IF NOT EXISTS users(
    tg_id INTEGER PRIMARY KEY, 
    username TEXT, 
    balance INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0
)""")
conn.execute("""CREATE TABLE IF NOT EXISTS inventory(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER, 
    item_id TEXT
)""")
conn.execute("""CREATE TABLE IF NOT EXISTS matches(
    match_id TEXT PRIMARY KEY,
    p1_id INTEGER, 
    p2_id INTEGER,
    p1_score INTEGER DEFAULT 0,
    p2_score INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active'
)""")
conn.commit()

# ==================== МАГАЗИН ====================
SHOP_ITEMS = {
    "chips": {"name": "Хрумка (чипсы)", "price": 50, "emoji": "🍟", "type": "food"},
    "cola": {"name": "Газява (кола)", "price": 100, "emoji": "🥤", "type": "food"},
    "hoodie": {"name": "Худи Balenciaga", "price": 5000, "emoji": "🧥", "type": "clothes"},
    "glasses": {"name": "Очки Gucci", "price": 3000, "emoji": "🕶", "type": "clothes"},
    "crown": {"name": "Корона Sigma", "price": 50000, "emoji": "👑", "type": "clothes"},
    "matiz": {"name": "Daewoo Matiz", "price": 10000, "emoji": "🚗", "type": "car"},
    "mers": {"name": "Mercedes-Benz", "price": 100000, "emoji": "🚘", "type": "car"},
    "tesla": {"name": "Tesla Cybertruck", "price": 500000, "emoji": "🛻", "type": "car"},
}

waiting_player = None
match_timers = {}

# ==================== УТИЛИТЫ ====================
def get_user(tg_id, username):
    # Используем conn.execute вместо cur.execute для потокобезопасности
    user = conn.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()
    if not user:
        conn.execute("INSERT INTO users(tg_id, username) VALUES(?, ?)", (tg_id, username))
        conn.commit()
        return get_user(tg_id, username)
    return user

def get_inventory(tg_id):
    return [row[0] for row in conn.execute("SELECT item_id FROM inventory WHERE tg_id=?", (tg_id,)).fetchall()]

def fmt(num):
    return f"{num:,}".replace(",", " ")

def get_main_menu(tg_id, username):
    user = get_user(tg_id, username)
    balance = user[2]
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"🐹 Тапнуть (+1)", callback_data="tap"),
        types.InlineKeyboardButton("🛒 Магазин", callback_data="shop")
    )
    markup.add(
        types.InlineKeyboardButton("🎒 Инвентарь", callback_data="inv"),
        types.InlineKeyboardButton("⚔️ Тап-Тап (PvP)", callback_data="find_match")
    )
    
    text = (
        f"👑 **ULTRA AURA SIGMA HAMSTER** 👑\n\n"
        f"👤 Игрок: @{username or 'Аноним'}\n"
        f"💰 Баланс: {fmt(balance)} 🪙\n"
        f"🏆 Побед: {user[3]} | 💀 Поражений: {user[4]}\n\n"
        f"Тапай хомяка, покупай чипсы, кока-колу и брендовые шмотки!"
    )
    return text, markup

def send_main_menu(chat_id, tg_id, username, edit=False, message_id=None):
    text, markup = get_main_menu(tg_id, username)
    try:
        if edit and message_id:
            bot.edit_message_caption(chat_id=chat_id, message_id=message_id, caption=text, reply_markup=markup, parse_mode="Markdown")
        else:
            with open("hamster.jpg", "rb") as photo:
                bot.send_photo(chat_id, photo, caption=text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        if edit and message_id:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

# ==================== ХЕНДЛЕРЫ ====================

@bot.message_handler(commands=['start'])
def start(m):
    get_user(m.from_user.id, m.from_user.username)
    bot.send_message(m.chat.id, "Загружаем хомяка... 🐹")
    time.sleep(0.5)
    send_main_menu(m.chat.id, m.from_user.id, m.from_user.username)

@bot.callback_query_handler(func=lambda call: call.data == "back_menu")
def back_menu(call):
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass
    send_main_menu(call.message.chat.id, call.from_user.id, call.from_user.username)

@bot.callback_query_handler(func=lambda call: call.data == "tap")
def tap_hamster(call):
    user = get_user(call.from_user.id, call.from_user.username)
    conn.execute("UPDATE users SET balance = balance + 1 WHERE tg_id=?", (call.from_user.id,))
    conn.commit()
    
    bot.answer_callback_query(call.id, "🐹 +1 тап!")
    
    new_balance = user[2] + 1
    if new_balance % 10 == 0:
        text, markup = get_main_menu(call.from_user.id, call.from_user.username)
        try:
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")
        except: pass

# ==================== МАГАЗИН ====================
@bot.callback_query_handler(func=lambda call: call.data == "shop")
def shop_menu(call):
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for item_id, item in SHOP_ITEMS.items():
        markup.add(types.InlineKeyboardButton(
            f"{item['emoji']} {item['name']} — {fmt(item['price'])} 🪙", 
            callback_data=f"buy_{item_id}"
        ))
        
    markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_menu"))
    bot.edit_message_caption(
        chat_id=call.message.chat.id, 
        message_id=call.message.message_id, 
        caption="🛒 **Магазин Хомяка**\n\nВыбирай, что купить:", 
        reply_markup=markup, 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def buy_item(call):
    item_id = call.data.split("_")[1]
    item = SHOP_ITEMS.get(item_id)
    if not item: return
    
    user = get_user(call.from_user.id, call.from_user.username)
    balance = user[2]
    
    if balance < item['price']:
        return bot.answer_callback_query(call.id, f"❌ Не хватает монет! Нужно {fmt(item['price'])} 🪙", show_alert=True)
        
    conn.execute("UPDATE users SET balance = balance - ? WHERE tg_id=?", (item['price'], call.from_user.id))
    conn.execute("INSERT INTO inventory(tg_id, item_id) VALUES(?, ?)", (call.from_user.id, item_id))
    conn.commit()
    
    bot.answer_callback_query(call.id, f"✅ Куплено: {item['name']}!")
    text, markup = get_main_menu(call.from_user.id, call.from_user.username)
    try:
        bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")
    except: pass

@bot.callback_query_handler(func=lambda call: call.data == "inv")
def inventory_menu(call):
    inv = get_inventory(call.from_user.id)
    if not inv:
        txt = "🎒 **Инвентарь пуст**\n\nКупи что-нибудь в магазине!"
    else:
        counts = {}
        for i in inv:
            counts[i] = counts.get(i, 0) + 1
        txt = "🎒 **Твой Инвентарь:**\n\n"
        for item_id, count in counts.items():
            item = SHOP_ITEMS.get(item_id)
            if item:
                txt += f"{item['emoji']} {item['name']} — x{count}\n"
                
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_menu"))
    bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=txt, reply_markup=markup, parse_mode="Markdown")

# ==================== PVP ТАП-ТАП ====================
@bot.callback_query_handler(func=lambda call: call.data == "find_match")
def find_match(call):
    global waiting_player
    
    if waiting_player and waiting_player['tg_id'] == call.from_user.id:
        return bot.answer_callback_query(call.id, "⏳ Ты уже в очереди. Ждем соперника...", show_alert=True)
        
    if not waiting_player:
        waiting_player = {'tg_id': call.from_user.id, 'username': call.from_user.username, 'chat_id': call.message.chat.id}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Отменить", callback_data="cancel_match"))
        bot.edit_message_caption(
            chat_id=call.message.chat.id, 
            message_id=call.message.message_id, 
            caption="⏳ **Поиск соперника...**\n\nЖдем, пока кто-то нажмет «Тап-Тап».", 
            reply_markup=markup
        )
        return

    p1 = waiting_player
    p2 = {'tg_id': call.from_user.id, 'username': call.from_user.username, 'chat_id': call.message.chat.id}
    waiting_player = None 
    
    match_id = str(int(time.time())) + str(random.randint(100, 999))
    conn.execute("INSERT INTO matches(match_id, p1_id, p2_id) VALUES(?, ?, ?)", (match_id, p1['tg_id'], p2['tg_id']))
    conn.commit()
    
    for p in [p1, p2]:
        enemy = p2['username'] if p['tg_id'] == p1['tg_id'] else p1['username']
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🐹 БЫСТРО ТАПАТЬ!", callback_data=f"match_tap_{match_id}"))
        
        try:
            bot.send_message(
                p['chat_id'], 
                f"⚔️ **МАТЧ НАЙДЕН!**\n\nТвой противник: @{enemy}\n\nУ тебя **10 секунд**, чтобы натапать больше всех!\nЖми кнопку со всей силы!", 
                reply_markup=markup, 
                parse_mode="Markdown"
            )
        except: pass
    
    timer = threading.Timer(10.0, finish_match, args=[match_id, p1, p2])
    match_timers[match_id] = timer
    timer.start()

@bot.callback_query_handler(func=lambda call: call.data == "cancel_match")
def cancel_match(call):
    global waiting_player
    if waiting_player and waiting_player['tg_id'] == call.from_user.id:
        waiting_player = None
    bot.answer_callback_query(call.id, "Поиск отменен")
    send_main_menu(call.message.chat.id, call.from_user.id, call.from_user.username)

@bot.callback_query_handler(func=lambda call: call.data.startswith("match_tap_"))
def match_tap(call):
    match_id = call.data.split("_")[2]
    
    match = conn.execute("SELECT status, p1_id, p2_id FROM matches WHERE match_id=?", (match_id,)).fetchone()
    
    if not match or match[0] != 'active':
        return bot.answer_callback_query(call.id, "Матч уже завершен!")
        
    p1_id, p2_id = match[1], match[2]
    
    if call.from_user.id == p1_id:
        conn.execute("UPDATE matches SET p1_score = p1_score + 1 WHERE match_id=?", (match_id,))
    elif call.from_user.id == p2_id:
        conn.execute("UPDATE matches SET p2_score = p2_score + 1 WHERE match_id=?", (match_id,))
    conn.commit()
    
    bot.answer_callback_query(call.id, "🐹 Тап!")

def finish_match(match_id, p1, p2):
    scores = conn.execute("SELECT p1_score, p2_score FROM matches WHERE match_id=?", (match_id,)).fetchone()
    if not scores: return
    
    p1_s, p2_s = scores[0], scores[1]
    conn.execute("UPDATE matches SET status='finished' WHERE match_id=?", (match_id,))
    
    if p1_s > p2_s:
        winner, loser = p1, p2
        w_score, l_score = p1_s, p2_s
    elif p2_s > p1_s:
        winner, loser = p2, p1
        w_score, l_score = p2_s, p1_s
    else:
        for p, score in [(p1, p1_s), (p2, p2_s)]:
            reward = score * 2
            conn.execute("UPDATE users SET balance = balance + ? WHERE tg_id=?", (reward, p['tg_id']))
            try:
                bot.send_message(p['chat_id'], f"🤝 **НИЧЬЯ!**\n\nСчет: {p1_s} - {p2_s}\nТы получаешь {fmt(reward)} 🪙", parse_mode="Markdown")
            except: pass
        conn.commit()
        return

    winner_reward = w_score * 5
    loser_reward = l_score * 1
    
    conn.execute("UPDATE users SET balance = balance + ?, wins = wins + 1 WHERE tg_id=?", (winner_reward, winner['tg_id']))
    conn.execute("UPDATE users SET balance = balance + ?, losses = losses + 1 WHERE tg_id=?", (loser_reward, loser['tg_id']))
    conn.commit()
    
    try:
        bot.send_message(winner['chat_id'], f"🏆 **ПОБЕДА!**\n\nСчет: {w_score} - {l_score}\nТы получаешь {fmt(winner_reward)} 🪙", parse_mode="Markdown")
        bot.send_message(loser['chat_id'], f"💀 **ПОРАЖЕНИЕ!**\n\nСчет: {l_score} - {w_score}\nТы получаешь {fmt(loser_reward)} 🪙", parse_mode="Markdown")
    except: pass
    
    match_timers.pop(match_id, None)

# Запуск
if __name__ == "__main__":
    print("Sigma Hamster запущен...")
    # Заменили infinity_polling на polling для старых версий
    bot.polling(none_stop=True, interval=0, timeout=60)