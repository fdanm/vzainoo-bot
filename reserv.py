import asyncio
import sqlite3
from aiogram import types, Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from datetime import datetime, timedelta
import logging

API_TOKEN = '7692188396:AAFQcjzCqFHITJrNyPNOng9_RtfpysdWZlw'
REQUIRED_CHANNEL = "@grifci"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

# --- Создание таблиц ---
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


# --- FSM для добавления канала ---
class AddChannel(StatesGroup):
    url = State()
    target = State()
    cost = State()


# --- Проверка подписки на обязательный канал ---
async def is_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status != ChatMemberStatus.LEFT
    except Exception as e:
        print(f"Ошибка: {e}")
        return False



# --- Автоматическое добавление пользователя в базу ---
async def ensure_user_in_db(user_id: int, referral_id: int = None):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone() is None:
        cursor.execute(
            "INSERT INTO users (user_id, tokens, join_date, referral_id) VALUES (?, ?, ?, ?)",
            (user_id, 0, datetime.now().isoformat(), referral_id)
        )
        conn.commit()


# --- Главное меню (редактируем сообщение, если возможно) ---
async def main_menu(target):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Заработать токены", callback_data="earn")],
        [InlineKeyboardButton(text="📢 Разместить канал", callback_data="place")],
        [InlineKeyboardButton(text="💰 Мои токены", callback_data="balance")],
        [InlineKeyboardButton(text="🎁 Пригласить друга", callback_data="ref")],
        [InlineKeyboardButton(text="🪙 Ежедневный бонус", callback_data="bonus")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")]
    ])
    text = "Выберите действие:"
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    elif isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb)
        except Exception:
            await target.message.answer(text, reply_markup=kb)


# --- /start с кнопкой проверки подписки ---
@dp.message(F.text.startswith("/start"))
async def cmd_start(msg: Message, state: FSMContext):
    user_id = msg.from_user.id

    subscribed = await is_subscribed(bot, user_id)

    if subscribed:
        await ensure_user_in_db(user_id)
        await msg.answer("👋 Добро пожаловать! Вы уже подписаны на канал.")
        await main_menu(msg)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_subscribe")]
        ])
        await msg.answer(
            f"🔒 Чтобы пользоваться ботом, подпишитесь на канал:\nhttps://t.me/{REQUIRED_CHANNEL.lstrip('@')}\n\n"
            "После подписки нажмите кнопку ниже.",
            reply_markup=kb
        )


@dp.callback_query(F.data == "check_subscribe")
async def check_subscription(cb: CallbackQuery):
    user_id = cb.from_user.id
    subscribed = await is_subscribed(bot, user_id)
    if subscribed:
        await ensure_user_in_db(user_id)
        await cb.message.edit_text("Спасибо за подписку! Добро пожаловать!")
        await main_menu(cb)
    else:
        await cb.answer("❌ Вы еще не подписались на канал, пожалуйста, подпишитесь.", show_alert=True)


# --- Команда /help и кнопка "Помощь" ---
HELP_TEXT = """
📌 **Инструкция по добавлению вашего Telegram-канала в бота взаимных подписок**

1. Подпишитесь на обязательный канал бота: https://t.me/grifci

2. Добавьте бота в свой канал и назначьте его администратором.

3. Убедитесь, что бот имеет права для проверки подписчиков.

4. В боте выберите "📢 Разместить канал", укажите ссылку на канал, количество подписчиков и токены.

5. Дождитесь, когда пользователи начнут подписываться на ваш канал.

⚠️ Внимание:
- Добавляйте бота только в каналы, которыми управляете.
- Не удаляйте бота из канала.
- Пользователи должны подтверждать подписку через бота.
- За отписки могут быть штрафы токенами.
"""

@dp.message(F.text == "/help")
async def cmd_help(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="menu")]
    ])
    await msg.answer(HELP_TEXT, reply_markup=kb)

@dp.callback_query(F.data == "help")
async def help_callback(cb: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="menu")]
    ])
    await cb.message.edit_text(HELP_TEXT, reply_markup=kb)


# --- Вернуться в меню ---
@dp.callback_query(F.data == "menu")
async def back_to_menu(cb: CallbackQuery):
    await main_menu(cb)


# --- Баланс токенов ---
@dp.callback_query(F.data == "balance")
async def balance(cb: CallbackQuery):
    user_id = cb.from_user.id
    cursor.execute("SELECT tokens FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    tokens = row[0] if row else 0
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="menu")]
    ])
    await cb.message.edit_text(f"💰 У тебя {tokens} токенов.", reply_markup=kb)
    await cb.answer()


# --- Добавление канала ---
@dp.callback_query(F.data == "place")
async def place_channel(cb: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="menu")]
    ])
    await cb.message.edit_text("🔗 Введите ссылку на канал:", reply_markup=kb)
    await state.set_state(AddChannel.url)
    await cb.answer()

@dp.message(AddChannel.url)
async def add_url(msg: Message, state: FSMContext):
    url = msg.text
    if not url.startswith("https://t.me/"):
        await msg.answer("❌ Укажите корректную ссылку на Telegram-канал.")
        return

    username = url.split("https://t.me/")[-1]
    try:
        member = await bot.get_chat_member(chat_id=f"@{username}", user_id=msg.from_user.id)
    except Exception:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="menu")]
        ])
        await msg.answer("❌ Бот должен быть добавлен в канал и назначен администратором!", reply_markup=kb)
        return

    await state.update_data(url=url)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="menu")]
    ])
    await msg.answer("👥 Сколько подписчиков хотите?", reply_markup=kb)
    await state.set_state(AddChannel.target)

@dp.message(AddChannel.target)
async def add_target(msg: Message, state: FSMContext):
    try:
        target = int(msg.text)
        if target <= 0:
            raise ValueError
    except:
        await msg.answer("❌ Введите корректное число подписчиков.")
        return

    await state.update_data(target=target)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="menu")]
    ])
    await msg.answer("💰 Сколько токенов вы готовы потратить? (1 подписчик = 1 токен)", reply_markup=kb)
    await state.set_state(AddChannel.cost)

@dp.message(AddChannel.cost)
async def add_cost(msg: Message, state: FSMContext):
    try:
        cost = int(msg.text)
        if cost <= 0:
            raise ValueError
    except:
        await msg.answer("❌ Введите корректное количество токенов.")
        return

    data = await state.get_data()
    url = data.get("url")
    target = data.get("target")
    user_id = msg.from_user.id

    cursor.execute("SELECT tokens FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    tokens = row[0] if row else 0
    if tokens < cost:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="menu")]
        ])
        await msg.answer("❌ У вас недостаточно токенов.", reply_markup=kb)
        return


    data = await state.get_data()
    url = data.get("url")
    target = data.get("target")
    user_id = msg.from_user.id

    cursor.execute("SELECT tokens FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    tokens = row[0] if row else 0
    if tokens < cost:
        await msg.answer("❌ У вас недостаточно токенов.")
        return

    cursor.execute("INSERT INTO channels (owner_id, url, target, cost) VALUES (?, ?, ?, ?)",
                   (user_id, url, target, cost))
    cursor.execute("UPDATE users SET tokens = tokens - ? WHERE user_id = ?", (cost, user_id))
    conn.commit()

    await msg.answer("✅ Канал добавлен в очередь. Пользователи начнут подписываться скоро.")
    await state.clear()


# --- Ежедневный бонус ---
@dp.callback_query(F.data == "bonus")
async def daily_bonus(cb: CallbackQuery):
    user_id = cb.from_user.id
    now = datetime.now()

    cursor.execute("SELECT last_bonus FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if row is None or row[0] is None:
        cursor.execute(
            "UPDATE users SET tokens = tokens + 1, last_bonus = ? WHERE user_id = ?",
            (now.isoformat(), user_id)
        )
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO users (user_id, tokens, last_bonus) VALUES (?, ?, ?)",
                (user_id, 1, now.isoformat())
            )
        conn.commit()
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="menu")]
        ])
        await cb.message.edit_text("🎁 Ты получил 1 токен за ежедневный вход!", reply_markup=kb)
        await cb.answer()
        return

    last_time = datetime.fromisoformat(row[0])
    if now - last_time < timedelta(hours=24):
        await cb.answer("❌ Бонус уже получен. Возвращайся позже!", show_alert=True)
        return

    cursor.execute(
        "UPDATE users SET tokens = tokens + 1, last_bonus = ? WHERE user_id = ?",
        (now.isoformat(), user_id)
    )
    conn.commit()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="menu")]
    ])
    await cb.message.edit_text("🎁 Ты получил 1 токен за ежедневный вход!", reply_markup=kb)
    await cb.answer()


# --- Реферальная ссылка ---
@dp.callback_query(F.data == "ref")
async def send_ref(cb: CallbackQuery):
    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start=ref={cb.from_user.id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="menu")]
    ])
    await cb.message.edit_text(f"🔗 Твоя реферальная ссылка:\n{ref_link}", reply_markup=kb)
    await cb.answer()


# --- Заработать токены (взаимные подписки) ---
@dp.callback_query(F.data == "earn")
async def earn_tokens(cb: CallbackQuery):
    user_id = cb.from_user.id
    cursor.execute("SELECT ban_until FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row and row[0] is not None:
        ban_until = datetime.fromisoformat(row[0])
        if ban_until > datetime.now():
            await cb.answer("🚫 Вы в бане за отписку. Попробуйте позже.", show_alert=True)
            return

    cursor.execute('''
        SELECT * FROM channels
        WHERE active = 1 AND current < target
        ORDER BY id ASC
    ''')
    row = cursor.fetchone()
    if row is None:
        await cb.answer("😔 Нет доступных каналов. Попробуйте позже.", show_alert=True)
        return

    channel_id, owner_id, url, target, current, cost, active = row
    cursor.execute("SELECT * FROM actions WHERE user_id = ? AND channel_id = ?", (user_id, channel_id))
    if cursor.fetchone():
        await cb.answer("🔄 Ты уже выполнял это задание. Подожди новые каналы.", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я подписался", callback_data=f"verify_{channel_id}")],
        [InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="menu")]
    ])
    await cb.message.edit_text(f"📢 Подпишись на канал: {url}\n\nНажми 'Я подписался' после этого.", reply_markup=kb)
    await cb.answer()


# --- Проверка подписки ---
@dp.callback_query(F.data.startswith("verify_"))
async def verify_subscription(cb: CallbackQuery):
    user_id = cb.from_user.id
    channel_id = int(cb.data.split("_")[1])

    cursor.execute("SELECT url, owner_id FROM channels WHERE id = ?", (channel_id,))
    row = cursor.fetchone()
    if not row:
        await cb.answer("❌ Канал не найден.", show_alert=True)
        return
    url, owner_id = row
    username = url.split("https://t.me/")[-1]

    try:
        member = await bot.get_chat_member(chat_id=f"@{username}", user_id=user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            cursor.execute("INSERT INTO actions (user_id, channel_id, timestamp, verified) VALUES (?, ?, ?, 1)",
                           (user_id, channel_id, datetime.now()))
            cursor.execute("UPDATE users SET tokens = tokens + 1 WHERE user_id = ?", (user_id,))
            cursor.execute("UPDATE channels SET current = current + 1 WHERE id = ?", (channel_id,))
            conn.commit()
            await cb.message.edit_text("✅ Подписка проверена. Токен начислен!", reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="menu")]]
            ))
            # Уведомление владельцу канала
            try:
                await bot.send_message(owner_id, f"🔔 На ваш канал {url} подписался пользователь @{cb.from_user.username or user_id}")
            except:
                pass
        else:
            await cb.answer("❌ Подписка не найдена. Подпишитесь и нажмите кнопку ещё раз.", show_alert=True)
    except:
        await cb.answer("⚠️ Не удалось проверить подписку. Попробуйте позже.", show_alert=True)


# --- Фоновая проверка отписок ---
async def check_unsubscribes():
    while True:
        now = datetime.now()
        cutoff = now - timedelta(hours=48)
        cursor.execute("SELECT user_id, channel_id, timestamp, verified FROM actions WHERE verified = 1 AND timestamp < ?", (cutoff.isoformat(),))
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
                    # Штраф токенов и бан
                    cursor.execute("UPDATE users SET tokens = tokens - 2, ban_until = ? WHERE user_id = ?", ( (now + timedelta(hours=24)).isoformat(), user_id))
                    conn.commit()
            except:
                continue
        await asyncio.sleep(3600)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    loop.create_task(check_unsubscribes())
    loop.run_until_complete(dp.start_polling(bot))
