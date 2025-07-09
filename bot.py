import asyncio
import sqlite3
from aiogram import types
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
import logging

REQUIRED_CHANNEL = "@grifci"

async def is_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception:
        return False

API_TOKEN = '7692188396:AAFQcjzCqFHITJrNyPNOng9_RtfpysdWZlw'
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    tokens INTEGER DEFAULT 0,
    last_check TIMESTAMP,
    referral_id INTEGER,
    ban_until TIMESTAMP,
    join_date TIMESTAMP,
    last_bonus TIMESTAMP
)''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER,
    url TEXT,
    target INTEGER,
    current INTEGER DEFAULT 0,
    cost INTEGER,
    active INTEGER DEFAULT 1
)''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS actions (
    user_id INTEGER,
    channel_id INTEGER,
    timestamp TIMESTAMP,
    verified INTEGER DEFAULT 0
)''')
conn.commit()

# --- Новая функция добавления пользователя в базу, если его нет ---
def ensure_user_in_db(user_id: int):
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO users (user_id, tokens, join_date) VALUES (?, ?, ?)",
                       (user_id, 0, datetime.now()))
        conn.commit()

class AddChannel(StatesGroup):
    url = State()
    target = State()
    cost = State()

# --- Главное меню и кнопка "вернуться в меню" ---
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Заработать токены", callback_data="earn")],
        [InlineKeyboardButton(text="📢 Разместить канал", callback_data="place")],
        [InlineKeyboardButton(text="💰 Мои токены", callback_data="balance")],
        [InlineKeyboardButton(text="🎁 Пригласить друга", callback_data="ref")],
        [InlineKeyboardButton(text="🪙 Ежедневный бонус", callback_data="bonus")]
    ])

def back_to_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="menu")]
    ])

# --- Обработчики ---

@dp.message(F.text.startswith("/start"))
async def cmd_start(msg: Message, state: FSMContext):
    if not await is_subscribed(bot, msg.from_user.id):
        await msg.answer("🔒 Чтобы пользоваться ботом, подпишитесь на канал:\nhttps://t.me/grifci")
        return

    user_id = msg.from_user.id
    ensure_user_in_db(user_id)

    ref_id = None
    if "?ref=" in msg.text:
        try:
            ref_id = int(msg.text.split("?ref=")[1])
        except:
            pass

    cursor.execute("SELECT referral_id FROM users WHERE user_id = ?", (user_id,))
    current_ref = cursor.fetchone()[0]
    if current_ref is None and ref_id is not None and ref_id != user_id:
        cursor.execute("UPDATE users SET referral_id = ? WHERE user_id = ?", (ref_id, user_id))
        cursor.execute("UPDATE users SET tokens = tokens + 3 WHERE user_id = ?", (ref_id,))
        try:
            await bot.send_message(ref_id, f"🎉 По вашей ссылке зашёл пользователь @{msg.from_user.username or user_id}!")
        except:
            pass
        conn.commit()
        await msg.answer(f"👋 Вас пригласил пользователь ID {ref_id}!\n\n🤖 Этот бот создан для взаимных подписок. Зарабатывайте токены, подписываясь на каналы, и продвигайте свои! 💥")
    else:
        await msg.answer("👋 Привет! Этот бот создан для взаимных подписок. Подписывайся на каналы, зарабатывай токены и размещай свои!")

    # Показываем меню, НЕ отправляем новое сообщение, а редактируем, если возможно
    await main_menu(msg)

async def main_menu(msg_or_cb):
    # msg_or_cb может быть Message или CallbackQuery
    kb = main_menu_kb()
    text = "Выберите действие:"

    if isinstance(msg_or_cb, Message):
        await msg_or_cb.answer(text, reply_markup=kb)
    elif isinstance(msg_or_cb, CallbackQuery):
        await msg_or_cb.message.edit_text(text, reply_markup=kb)
        await msg_or_cb.answer()

# Обработка кнопки меню (возврат в меню)
@dp.callback_query(F.data == "menu")
async def back_to_menu(cb: CallbackQuery):
    ensure_user_in_db(cb.from_user.id)
    await main_menu(cb)

# Остальные обработчики — вызываем ensure_user_in_db и заменяем send -> edit_message_text там, где нужно

@dp.callback_query(F.data == "balance")
async def balance(cb: CallbackQuery):
    ensure_user_in_db(cb.from_user.id)
    cursor.execute("SELECT tokens FROM users WHERE user_id = ?", (cb.from_user.id,))
    tokens = cursor.fetchone()[0]
    await cb.message.edit_text(f"💰 У тебя {tokens} токенов.", reply_markup=back_to_menu_kb())
    await cb.answer()

@dp.callback_query(F.data == "place")
async def place_channel(cb: CallbackQuery, state: FSMContext):
    ensure_user_in_db(cb.from_user.id)
    await cb.message.edit_text("🔗 Введите ссылку на канал:", reply_markup=back_to_menu_kb())
    await state.set_state(AddChannel.url)
    await cb.answer()

@dp.message(AddChannel.url)
async def add_url(msg: Message, state: FSMContext):
    ensure_user_in_db(msg.from_user.id)
    url = msg.text
    if not url.startswith("https://t.me/"):
        await msg.answer("❌ Укажите корректную ссылку на Telegram-канал.")
        return

    username = url.split("https://t.me/")[-1]
    try:
        member = await bot.get_chat_member(chat_id=f"@{username}", user_id=msg.from_user.id)
    except:
        await msg.answer("❌ Бот должен быть добавлен в канал и назначен администратором!")
        return

    await state.update_data(url=url)
    await msg.answer("👥 Сколько подписчиков хотите?")
    await state.set_state(AddChannel.target)

@dp.message(AddChannel.target)
async def add_target(msg: Message, state: FSMContext):
    ensure_user_in_db(msg.from_user.id)
    await state.update_data(target=int(msg.text))
    await msg.answer("💰 Сколько токенов вы готовы потратить? (1 подписчик = 1 токен)")
    await state.set_state(AddChannel.cost)

@dp.message(AddChannel.cost)
async def add_cost(msg: Message, state: FSMContext):
    ensure_user_in_db(msg.from_user.id)
    data = await state.get_data()
    url = data["url"]
    target = data["target"]
    cost = int(msg.text)
    user_id = msg.from_user.id

    cursor.execute("SELECT tokens FROM users WHERE user_id = ?", (user_id,))
    tokens = cursor.fetchone()[0]
    if tokens < cost:
        await msg.answer("❌ У вас недостаточно токенов.")
        return

    cursor.execute("INSERT INTO channels (owner_id, url, target, cost) VALUES (?, ?, ?, ?)",
                   (user_id, url, target, cost))
    cursor.execute("UPDATE users SET tokens = tokens - ? WHERE user_id = ?", (cost, user_id))
    conn.commit()

    await msg.answer("✅ Канал добавлен в очередь. Пользователи начнут подписываться скоро.")
    await state.clear()

@dp.callback_query(F.data == "bonus")
async def daily_bonus(cb: CallbackQuery):
    ensure_user_in_db(cb.from_user.id)
    user_id = cb.from_user.id
    now = datetime.now()

    cursor.execute("SELECT last_bonus FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if row is None:
        cursor.execute(
            "INSERT INTO users (user_id, tokens, last_bonus) VALUES (?, ?, ?)",
            (user_id, 1, now.isoformat())
        )
        conn.commit()
        await cb.message.edit_text("🎁 Ты получил 1 токен за ежедневный вход!", reply_markup=back_to_menu_kb())
        await cb.answer()
        return

    if row[0] is not None:
        last_time = datetime.fromisoformat(row[0])
        if now - last_time < timedelta(hours=24):
            await cb.message.edit_text("❌ Бонус уже получен. Возвращайся позже!", reply_markup=back_to_menu_kb())
            await cb.answer()
            return

    cursor.execute(
        "UPDATE users SET tokens = tokens + 1, last_bonus = ? WHERE user_id = ?", 
        (now.isoformat(), user_id)
    )
    conn.commit()
    await cb.message.edit_text("🎁 Ты получил 1 токен за ежедневный вход!", reply_markup=back_to_menu_kb())
    await cb.answer()

@dp.callback_query(F.data == "ref")
async def send_ref(cb: CallbackQuery):
    ensure_user_in_db(cb.from_user.id)
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref={cb.from_user.id}"
    await cb.message.edit_text(f"🔗 Твоя реферальная ссылка:\n{ref_link}", reply_markup=back_to_menu_kb())
    await cb.answer()

@dp.callback_query(F.data == "earn")
async def earn_tokens(cb: CallbackQuery):
    ensure_user_in_db(cb.from_user.id)
    user_id = cb.from_user.id
    cursor.execute("SELECT * FROM users WHERE user_id = ? AND ban_until IS NOT NULL AND ban_until > ?", (user_id, datetime.now()))
    if cursor.fetchone():
        await cb.message.edit_text("🚫 Вы в бане за отписку. Попробуйте позже.", reply_markup=back_to_menu_kb())
        await cb.answer()
        return

    cursor.execute('''
        SELECT * FROM channels
        WHERE active = 1 AND current < target
        ORDER BY id ASC
    ''')
    row = cursor.fetchone()
    if row is None:
        await cb.message.edit_text("😔 Нет доступных каналов. Попробуйте позже.", reply_markup=back_to_menu_kb())
        await cb.answer()
        return

    channel_id, owner_id, url, target, current, cost, active = row
    cursor.execute("SELECT * FROM actions WHERE user_id = ? AND channel_id = ?", (user_id, channel_id))
    if cursor.fetchone():
        await cb.message.edit_text("🔄 Ты уже выполнял это задание. Подожди новые каналы.", reply_markup=back_to_menu_kb())
        await cb.answer()
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я подписался", callback_data=f"verify_{channel_id}")],
        [InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="menu")]
    ])
    await cb.message.edit_text(f"📢 Подпишись на канал: {url}\n\nНажми 'Я подписался' после этого.", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("verify_"))
async def verify_subscription(cb: CallbackQuery):
    ensure_user_in_db(cb.from_user.id)
    user_id = cb.from_user.id
    channel_id = int(cb.data.split("_")[1])

    cursor.execute("SELECT url, owner_id FROM channels WHERE id = ?", (channel_id,))
    row = cursor.fetchone()
    if not row:
        await cb.message.edit_text("❌ Канал не найден.", reply_markup=back_to_menu_kb())
        await cb.answer()
        return
    url, owner_id = row
    username = url.split("https://t.me/")[-1]

    try:
        member = await bot.get_chat_member(chat_id=f"@{username}", user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            cursor.execute("INSERT INTO actions (user_id, channel_id, timestamp, verified) VALUES (?, ?, ?, 1)",
                           (user_id, channel_id, datetime.now()))
            cursor.execute("UPDATE users SET tokens = tokens + 1 WHERE user_id = ?", (user_id,))
            cursor.execute("UPDATE channels SET current = current + 1 WHERE id = ?", (channel_id,))
            conn.commit()
            await cb.message.edit_text("✅ Подписка проверена. Токен начислен!", reply_markup=back_to_menu_kb())

            try:
                await bot.send_message(owner_id, f"🔔 На ваш канал {url} подписался пользователь @{cb.from_user.username or user_id}")
            except:
                pass
        else:
            await cb.message.edit_text("❌ Подписка не найдена. Попробуй ещё раз после подписки.", reply_markup=back_to_menu_kb())
    except:
        await cb.message.edit_text("⚠️ Не удалось проверить подписку. Попробуй позже.", reply_markup=back_to_menu_kb())
    await cb.answer()

async def check_unsubscribes():
    while True:
        now = datetime.now()
        cutoff = now - timedelta(hours=48)
        cursor.execute("SELECT * FROM actions WHERE verified = 1 AND timestamp < ?", (cutoff,))
        actions = cursor.fetchall()
        for user_id, channel_id, timestamp, verified in actions:
            cursor.execute("SELECT url FROM channels WHERE id = ?", (channel_id,))
            row = cursor.fetchone()
            if not row:
                continue
            username = row[0].split("https://t.me/")[-1]
            try:
                member = await bot.get_chat_member(chat_id=f"@{username}", user_id=user_id)
                if member.status == "left":
                    cursor.execute("UPDATE users SET tokens = tokens - 2, ban_until = ? WHERE user_id = ?", (now + timedelta(hours=24), user_id))
                    conn.commit()
            except:
                continue
        await asyncio.sleep(3600)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    loop.create_task(check_unsubscribes())
    loop.run_until_complete(dp.start_polling(bot))
