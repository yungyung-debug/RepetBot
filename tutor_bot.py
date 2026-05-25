import sqlite3
import asyncio
import os
import shutil
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton,
                          ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, FSInputFile)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get('TOKEN', "8806820030:AAGtXs0DrqnS0jTTrVB3Fs5F5j5UAzYB8DQ")
REPETITOR_ID = int(os.environ.get('REPETITOR_ID', "709532378"))
# ===============================

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ========== БАЗА ДАННЫХ ==========
conn = sqlite3.connect("tutor_bot.db", check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц
cursor.execute("""
CREATE TABLE IF NOT EXISTS students (
    user_id INTEGER PRIMARY KEY,
    full_name TEXT,
    student_name TEXT,
    parent_id INTEGER,
    phone TEXT,
    schedule TEXT,
    paid_lessons INTEGER DEFAULT 0,
    completed_lessons INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS homework (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    teacher_id INTEGER,
    photo_id TEXT,
    caption TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'new',
    message_id INTEGER,
    chat_id INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    amount INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()

# ========== СОСТОЯНИЯ ДЛЯ FSM ==========
class AddStudent(StatesGroup):
    waiting_for_name = State()
    waiting_for_student_name = State()
    waiting_for_phone = State()

class AddPayment(StatesGroup):
    waiting_for_student_id = State()
    waiting_for_amount = State()

class CompleteLesson(StatesGroup):
    waiting_for_student_id = State()

class SetSchedule(StatesGroup):
    waiting_for_student_id = State()
    waiting_for_schedule = State()

class ReplyToHomework(StatesGroup):
    waiting_for_photo = State()
    waiting_for_text = State()

class TeacherSendPhoto(StatesGroup):
    waiting_for_student_id = State()

class WaitForBalance(StatesGroup):
    waiting_for_student_id = State()

# ========== КЛАВИАТУРЫ ==========

def student_keyboard():
    buttons = [
        [KeyboardButton(text="📅 Расписание")],
        [KeyboardButton(text="💰 Мой баланс")],
        [KeyboardButton(text="📤 Отправить домашку")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def teacher_keyboard():
    buttons = [
        [KeyboardButton(text="📊 Все ученики")],
        [KeyboardButton(text="➕ Добавить ученика")],
        [KeyboardButton(text="📝 Управление занятиями")],
        [KeyboardButton(text="📸 Просмотр домашек")],
        [KeyboardButton(text="🔧 Настройки")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== КОМАНДЫ ==========

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    
    cursor.execute("SELECT * FROM students WHERE user_id = ?", (user_id,))
    student = cursor.fetchone()
    
    if user_id == REPETITOR_ID:
        await message.answer(
            "👋 Здравствуйте, репетитор!\n\n"
            "Выберите действие в меню ниже:",
            reply_markup=teacher_keyboard()
        )
    elif student:
        await message.answer(
            f"👋 С возвращением, {student[2]}!\n\n"
            "Чем могу помочь?",
            reply_markup=student_keyboard()
        )
    else:
        await message.answer(
            "🎓 Добро пожаловать!\n\n"
            "Зарегистрируйтесь командой:\n"
            "/register Ваше_Имя Имя_Ученика Телефон\n\n"
            "Пример: /register Иван Иванов Петя +79991234567"
        )

@dp.message(Command("register"))
async def register_student(message: Message):
    try:
        parts = message.text.split(maxsplit=3)
        if len(parts) < 4:
            await message.answer("❌ Неверный формат!\n\nИспользуйте:\n/register Ваше_Имя Имя_Ученика Телефон")
            return
        
        full_name = parts[1]
        student_name = parts[2]
        phone = parts[3]
        user_id = message.from_user.id
        
        cursor.execute("""
            INSERT OR REPLACE INTO students (user_id, full_name, student_name, phone, paid_lessons, completed_lessons)
            VALUES (?, ?, ?, ?, 0, 0)
        """, (user_id, full_name, student_name, phone))
        conn.commit()
        
        await message.answer(
            f"✅ Регистрация успешна!\n\n"
            f"Родитель/ученик: {full_name}\n"
            f"Ученик: {student_name}\n"
            f"Телефон: {phone}\n\n"
            f"Теперь вы можете пользоваться ботом!",
            reply_markup=student_keyboard()
        )
        
        await bot.send_message(
            REPETITOR_ID,
            f"🆕 Новый ученик зарегистрировался!\n\n"
            f"Ученик: {student_name}\n"
            f"Родитель: {full_name}\n"
            f"Телефон: {phone}\n"
            f"ID: {user_id}"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message(Command("cancel"))
async def cancel_reply(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено")

@dp.message(Command("balance"))
async def quick_balance_check(message: Message):
    """Быстрая проверка баланса по команде /balance ID_ученика"""
    if message.from_user.id != REPETITOR_ID:
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer(
            "📊 *Быстрая проверка баланса*\n\n"
            "Используйте: `/balance ID_ученика`\n\n"
            "Пример: `/balance 123456789`",
            parse_mode="Markdown"
        )
        return
    
    try:
        student_id = int(parts[1])
        cursor.execute("""
            SELECT student_name, paid_lessons, completed_lessons 
            FROM students WHERE user_id = ?
        """, (student_id,))
        student = cursor.fetchone()
        
        if student:
            student_name, paid, completed = student
            left = paid - completed
            await message.answer(
                f"📊 *{student_name}*\n"
                f"✅ Оплачено: {paid}\n"
                f"📚 Проведено: {completed}\n"
                f"📈 Осталось: {left}",
                parse_mode="Markdown"
            )
        else:
            await message.answer(f"❌ Ученик с ID {student_id} не найден")
    except ValueError:
        await message.answer("❌ ID должен быть числом")

# ========== УЧЕНИЧЕСКИЕ КНОПКИ ==========

@dp.message(F.text == "📅 Расписание")
async def show_schedule(message: Message):
    cursor.execute("SELECT schedule, student_name FROM students WHERE user_id = ?", (message.from_user.id,))
    result = cursor.fetchone()
    
    if result and result[0]:
        await message.answer(f"📅 Расписание для {result[1]}:\n\n{result[0]}")
    else:
        await message.answer("📅 Расписание пока не задано. Обратитесь к репетитору.")

@dp.message(F.text == "💰 Мой баланс")
async def show_balance(message: Message):
    cursor.execute("SELECT paid_lessons, completed_lessons, student_name FROM students WHERE user_id = ?", 
                   (message.from_user.id,))
    result = cursor.fetchone()
    
    if result:
        paid, completed, name = result
        left = paid - completed
        
        await message.answer(
            f"💰 *Баланс занятий для {name}*\n\n"
            f"✅ Оплачено: {paid}\n"
            f"📚 Проведено: {completed}\n"
            f"📈 Осталось: {left}\n\n"
            f"💡 Когда остаток станет 0, вы получите напоминание об оплате.",
            parse_mode="Markdown"
        )
    else:
        await message.answer("❌ Вы не зарегистрированы! Используйте /register")

@dp.message(F.text == "📤 Отправить домашку")
async def send_homework(message: Message):
    await message.answer(
        "📤 Отправьте фото домашнего задания.\n\n"
        "Вы можете добавить комментарий к фото.\n"
        "Учитель получит уведомление."
    )

@dp.message(F.text == "ℹ️ Помощь")
async def help_student(message: Message):
    await message.answer(
        "📖 *Справка по боту*\n\n"
        "📅 Расписание - посмотреть расписание занятий\n"
        "💰 Мой баланс - проверить остаток занятий\n"
        "📤 Отправить домашку - отправить фото ДЗ\n\n"
        "По всем вопросам пишите репетитору.",
        parse_mode="Markdown"
    )

# ========== РЕПЕТИТОРСКИЕ КНОПКИ ==========

@dp.message(F.text == "📊 Все ученики")
async def show_all_students(message: Message):
    if message.from_user.id != REPETITOR_ID:
        return
    
    cursor.execute("SELECT user_id, student_name, full_name, phone, paid_lessons, completed_lessons FROM students")
    students = cursor.fetchall()
    
    if not students:
        await message.answer("📭 Пока нет зарегистрированных учеников.")
        return
    
    text = "📊 *Список учеников:*\n\n"
    for student in students:
        user_id, student_name, full_name, phone, paid, completed = student
        left = paid - completed
        text += f"👤 *{student_name}*\n"
        text += f"┣ ID: `{user_id}`\n"
        text += f"┣ Родитель: {full_name}\n"
        text += f"┣ 📞 {phone}\n"
        text += f"┣ ✅ Оплачено: {paid}\n"
        text += f"┣ 📚 Проведено: {completed}\n"
        text += f"┗ 📈 Осталось: {left}\n\n"
    
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await message.answer(text[i:i+4000], parse_mode="Markdown")
    else:
        await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "➕ Добавить ученика")
async def add_student_manual(message: Message, state: FSMContext):
    if message.from_user.id != REPETITOR_ID:
        return
    
    await message.answer("➕ Введите ФИО родителя/ученика:")
    await state.set_state(AddStudent.waiting_for_name)

@dp.message(AddStudent.waiting_for_name)
async def process_student_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("Введите имя ученика:")
    await state.set_state(AddStudent.waiting_for_student_name)

@dp.message(AddStudent.waiting_for_student_name)
async def process_student_student_name(message: Message, state: FSMContext):
    await state.update_data(student_name=message.text)
    await message.answer("Введите телефон для связи:")
    await state.set_state(AddStudent.waiting_for_phone)

@dp.message(AddStudent.waiting_for_phone)
async def process_student_phone(message: Message, state: FSMContext):
    data = await state.get_data()
    
    await message.answer(
        f"✅ Ученик добавлен в систему!\n\n"
        f"ФИО: {data['full_name']}\n"
        f"Ученик: {data['student_name']}\n"
        f"Телефон: {message.text}\n\n"
        f"❗️ Ученик должен зарегистрироваться в боте командой /register"
    )
    
    await state.clear()

@dp.message(F.text == "📝 Управление занятиями")
async def manage_lessons(message: Message):
    if message.from_user.id != REPETITOR_ID:
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Добавить оплату", callback_data="add_payment")],
        [InlineKeyboardButton(text="📚 Отметить проведенное занятие", callback_data="complete_lesson")],
        [InlineKeyboardButton(text="📅 Задать расписание", callback_data="set_schedule")],
        [InlineKeyboardButton(text="📊 Проверить баланс ученика", callback_data="check_balance")]
    ])
    
    await message.answer("📝 *Управление занятиями*\n\nВыберите действие:", reply_markup=keyboard, parse_mode="Markdown")

@dp.message(F.text == "📸 Просмотр домашек")
async def view_homeworks(message: Message):
    if message.from_user.id != REPETITOR_ID:
        return
    
    cursor.execute("""
        SELECT h.id, s.student_name, h.caption, h.timestamp, h.photo_id
        FROM homework h
        JOIN students s ON h.student_id = s.user_id
        WHERE h.status = 'new'
        ORDER BY h.timestamp DESC
    """)
    homeworks = cursor.fetchall()
    
    if not homeworks:
        await message.answer("📭 Нет новых домашних заданий.")
        return
    
    for hw in homeworks:
        hw_id, student_name, caption, timestamp, photo_id = hw
        text = f"📸 *Домашнее задание от {student_name}*\n🕐 {timestamp}\n"
        if caption:
            text += f"📝 {caption}\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отмечено", callback_data=f"mark_{hw_id}"),
                InlineKeyboardButton(text="📝 Ответить", callback_data=f"reply_{hw_id}")
            ]
        ])
        
        await bot.send_photo(REPETITOR_ID, photo_id, caption=text, reply_markup=keyboard, parse_mode="Markdown")

@dp.message(F.text == "🔧 Настройки")
async def settings(message: Message):
    if message.from_user.id != REPETITOR_ID:
        return
    
    cursor.execute("SELECT COUNT(*) FROM homework WHERE status = 'new'")
    new_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM homework WHERE status = 'viewed'")
    viewed_count = cursor.fetchone()[0]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text=f"🗑 Удалить просмотренные ({viewed_count})", callback_data="clear_viewed")],
        [InlineKeyboardButton(text=f"⚠️ Удалить ВСЕ ({new_count + viewed_count})", callback_data="clear_all")],
        [InlineKeyboardButton(text="💾 Резервная копия", callback_data="backup")]
    ])
    
    await message.answer(
        f"🔧 *Настройки бота*\n\n"
        f"📸 Новых: {new_count}\n"
        f"✅ Просмотренных: {viewed_count}\n"
        f"📦 Всего: {new_count + viewed_count}",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# ========== CALLBACK ОБРАБОТЧИКИ ==========

# Кнопка "Отмечено" - работает!
@dp.callback_query(F.data.startswith("mark_"))
async def mark_homework_done(callback: CallbackQuery):
    if callback.from_user.id != REPETITOR_ID:
        await callback.answer("❌ Только для репетитора", show_alert=True)
        return
    
    hw_id = int(callback.data.split("_")[1])
    
    cursor.execute("SELECT student_id, photo_id, caption FROM homework WHERE id = ?", (hw_id,))
    result = cursor.fetchone()
    
    if not result:
        await callback.answer("❌ Домашнее задание не найдено!", show_alert=True)
        return
    
    student_id, photo_id, caption = result
    
    cursor.execute("SELECT student_name FROM students WHERE user_id = ?", (student_id,))
    student_result = cursor.fetchone()
    student_name = student_result[0] if student_result else "Ученик"
    
    cursor.execute("UPDATE homework SET status = 'viewed' WHERE id = ?", (hw_id,))
    conn.commit()
    
    # Убираем кнопки у сообщения
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.edit_caption(
            caption=f"✅ ПРОВЕРЕНО ✅\n\n👤 {student_name}\n📝 {caption if caption else 'Нет комментария'}",
            reply_markup=None
        )
    except:
        pass
    
    # Уведомляем ученика
    try:
        await bot.send_message(
            student_id,
            f"✅ *Домашнее задание проверено!*\n\n"
            f"Репетитор проверил вашу работу. Молодец! 📚",
            parse_mode="Markdown"
        )
        await callback.answer("✅ Домашка отмечена! Ученик получил уведомление.")
    except Exception as e:
        await callback.answer("✅ Домашка отмечена, но ученик не в сети")

# Кнопка "Ответить"
@dp.callback_query(F.data.startswith("reply_"))
async def reply_to_homework(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != REPETITOR_ID:
        await callback.answer("❌ Только для репетитора", show_alert=True)
        return
    
    hw_id = int(callback.data.split("_")[1])
    
    cursor.execute("SELECT student_id FROM homework WHERE id = ?", (hw_id,))
    result = cursor.fetchone()
    
    if result:
        student_id = result[0]
        await state.update_data(reply_student_id=student_id)
        await state.set_state(ReplyToHomework.waiting_for_text)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Ответить фото/файлом", callback_data="reply_photo_mode")]
        ])
        
        await callback.message.answer(
            "✍️ Введите текст ответа для ученика:\n\n"
            "Или нажмите кнопку для отправки фото",
            reply_markup=keyboard
        )
        await callback.answer()
    else:
        await callback.answer("❌ Ошибка", show_alert=True)

# Переключение на фото-режим
@dp.callback_query(F.data == "reply_photo_mode")
async def reply_photo_mode(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ReplyToHomework.waiting_for_photo)
    await callback.message.answer("📸 Отправьте фото или файл для ученика:")
    await callback.answer()

# Текстовый ответ
@dp.message(ReplyToHomework.waiting_for_text, F.text)
async def process_text_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    student_id = data.get('reply_student_id')
    
    if not student_id:
        await message.answer("❌ Ошибка")
        await state.clear()
        return
    
    try:
        await bot.send_message(
            student_id,
            f"📢 *Ответ от репетитора на домашнее задание:*\n\n{message.text}",
            parse_mode="Markdown"
        )
        await message.answer("✅ Ответ отправлен ученику!")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# Фото-ответ
@dp.message(ReplyToHomework.waiting_for_photo, F.photo)
async def process_photo_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    student_id = data.get('reply_student_id')
    
    if not student_id:
        await message.answer("❌ Ошибка")
        await state.clear()
        return
    
    photo_id = message.photo[-1].file_id
    caption = message.caption or "Ответ на домашнее задание"
    
    try:
        await bot.send_photo(
            student_id,
            photo_id,
            caption=f"📢 *Ответ от репетитора:*\n\n{caption}",
            parse_mode="Markdown"
        )
        await message.answer("✅ Фото-ответ отправлен ученику!")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# Проверка баланса ученика (для репетитора)
@dp.callback_query(F.data == "check_balance")
async def check_balance_request(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != REPETITOR_ID:
        await callback.answer("❌ Только для репетитора", show_alert=True)
        return
    
    await callback.message.answer(
        "📊 *Проверка баланса ученика*\n\n"
        "Введите ID ученика (можно посмотреть в списке учеников):\n\n"
        "Пример: `123456789`\n\n"
        "Или используйте команду: `/balance 123456789`",
        parse_mode="Markdown"
    )
    await state.set_state(WaitForBalance.waiting_for_student_id)
    await callback.answer()

# Обработчик ввода ID для баланса
@dp.message(WaitForBalance.waiting_for_student_id, F.text)
async def process_balance_student_id(message: Message, state: FSMContext):
    if message.from_user.id != REPETITOR_ID:
        return
    
    try:
        student_id = int(message.text.strip())
        
        cursor.execute("""
            SELECT student_name, full_name, phone, paid_lessons, completed_lessons 
            FROM students WHERE user_id = ?
        """, (student_id,))
        student = cursor.fetchone()
        
        if student:
            student_name, full_name, phone, paid, completed = student
            left = paid - completed
            
            balance_text = (
                f"📊 *БАЛАНС УЧЕНИКА*\n\n"
                f"👤 *Имя ученика:* {student_name}\n"
                f"👨‍👩‍👧 *Родитель:* {full_name}\n"
                f"📞 *Телефон:* {phone}\n"
                f"🆔 *ID:* `{student_id}`\n\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"✅ *Оплачено занятий:* {paid}\n"
                f"📚 *Проведено занятий:* {completed}\n"
                f"📈 *Осталось занятий:* {left}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
            )
            
            if left <= 0:
                balance_text += "\n⚠️ **ВНИМАНИЕ! Нужно пополнить баланс!**"
            elif left <= 2:
                balance_text += "\n⚠️ Осталось мало занятий, скоро нужно будет пополнить."
            
            await message.answer(balance_text, parse_mode="Markdown")
        else:
            await message.answer(f"❌ Ученик с ID `{student_id}` не найден!", parse_mode="Markdown")
        
        await state.clear()
    except ValueError:
        await message.answer("❌ Ошибка: ID должен быть числом!", parse_mode="Markdown")
        await state.clear()

# Добавление оплаты
@dp.callback_query(F.data == "add_payment")
async def cb_add_payment(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("💰 Введите ID ученика:")
    await state.set_state(AddPayment.waiting_for_student_id)
    await callback.answer()

@dp.message(AddPayment.waiting_for_student_id)
async def process_payment_student_id(message: Message, state: FSMContext):
    try:
        student_id = int(message.text)
        cursor.execute("SELECT student_name FROM students WHERE user_id = ?", (student_id,))
        student = cursor.fetchone()
        
        if student:
            await state.update_data(student_id=student_id)
            await message.answer(f"Ученик: {student[0]}\n\nВведите количество оплаченных занятий:")
            await state.set_state(AddPayment.waiting_for_amount)
        else:
            await message.answer("❌ Ученик не найден!")
            await state.clear()
    except:
        await message.answer("❌ Введите число!")

@dp.message(AddPayment.waiting_for_amount)
async def process_payment_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
        data = await state.get_data()
        student_id = data['student_id']
        
        cursor.execute("UPDATE students SET paid_lessons = paid_lessons + ? WHERE user_id = ?", (amount, student_id))
        cursor.execute("INSERT INTO payments (student_id, amount) VALUES (?, ?)", (student_id, amount))
        conn.commit()
        
        cursor.execute("SELECT student_name FROM students WHERE user_id = ?", (student_id,))
        student_name = cursor.fetchone()[0]
        
        await message.answer(f"✅ Добавлено {amount} занятий для {student_name}")
        
        try:
            await bot.send_message(student_id, f"💰 Пополнение баланса!\n\nДобавлено {amount} занятий.")
        except:
            pass
        
        await state.clear()
    except:
        await message.answer("❌ Введите число!")

# Отметить проведенное занятие
@dp.callback_query(F.data == "complete_lesson")
async def cb_complete_lesson(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📚 Введите ID ученика:")
    await state.set_state(CompleteLesson.waiting_for_student_id)
    await callback.answer()

@dp.message(CompleteLesson.waiting_for_student_id)
async def process_complete_lesson(message: Message, state: FSMContext):
    try:
        student_id = int(message.text)
        cursor.execute("SELECT student_name, paid_lessons, completed_lessons FROM students WHERE user_id = ?", (student_id,))
        student = cursor.fetchone()
        
        if student:
            student_name, paid, completed = student
            new_completed = completed + 1
            left = paid - new_completed
            
            cursor.execute("UPDATE students SET completed_lessons = completed_lessons + 1 WHERE user_id = ?", (student_id,))
            conn.commit()
            
            await message.answer(f"✅ Отмечено занятие для {student_name}\nОсталось: {left}")
            
            try:
                await bot.send_message(student_id, f"📚 Проведено занятие!\n\nОсталось оплаченных занятий: {left}")
                if left <= 0:
                    await bot.send_message(student_id, "⚠️ ВНИМАНИЕ! У вас закончились оплаченные занятия. Пожалуйста, пополните баланс.")
            except:
                pass
            
            await state.clear()
        else:
            await message.answer("❌ Ученик не найден!")
            await state.clear()
    except:
        await message.answer("❌ Введите число!")

# Задать расписание
@dp.callback_query(F.data == "set_schedule")
async def cb_set_schedule(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📅 Введите ID ученика:")
    await state.set_state(SetSchedule.waiting_for_student_id)
    await callback.answer()

@dp.message(SetSchedule.waiting_for_student_id)
async def process_schedule_student_id(message: Message, state: FSMContext):
    try:
        student_id = int(message.text)
        cursor.execute("SELECT student_name FROM students WHERE user_id = ?", (student_id,))
        student = cursor.fetchone()
        
        if student:
            await state.update_data(student_id=student_id)
            await message.answer(f"Ученик: {student[0]}\n\nВведите расписание (например: Пн 16:00, Ср 18:30):")
            await state.set_state(SetSchedule.waiting_for_schedule)
        else:
            await message.answer("❌ Ученик не найден!")
            await state.clear()
    except:
        await message.answer("❌ Введите число!")

@dp.message(SetSchedule.waiting_for_schedule)
async def process_set_schedule(message: Message, state: FSMContext):
    data = await state.get_data()
    student_id = data['student_id']
    schedule = message.text
    
    cursor.execute("UPDATE students SET schedule = ? WHERE user_id = ?", (schedule, student_id))
    conn.commit()
    
    cursor.execute("SELECT student_name FROM students WHERE user_id = ?", (student_id,))
    student_name = cursor.fetchone()[0]
    
    await message.answer(f"✅ Расписание для {student_name} установлено:\n\n{schedule}")
    
    try:
        await bot.send_message(student_id, f"📅 Репетитор установил расписание:\n\n{schedule}")
    except:
        pass
    
    await state.clear()

# Статистика
@dp.callback_query(F.data == "stats")
async def show_stats(callback: CallbackQuery):
    if callback.from_user.id != REPETITOR_ID:
        return
    
    cursor.execute("SELECT COUNT(*) FROM students")
    students_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(paid_lessons) FROM students")
    total_paid = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(completed_lessons) FROM students")
    total_completed = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM homework WHERE status = 'new'")
    pending_hw = cursor.fetchone()[0]
    
    await callback.message.answer(
        f"📊 *Статистика*\n\n"
        f"👥 Учеников: {students_count}\n"
        f"✅ Оплачено занятий: {total_paid}\n"
        f"📚 Проведено занятий: {total_completed}\n"
        f"📸 Ждут проверки: {pending_hw}",
        parse_mode="Markdown"
    )
    await callback.answer()

# Удаление просмотренных
@dp.callback_query(F.data == "clear_viewed")
async def clear_viewed(callback: CallbackQuery):
    if callback.from_user.id != REPETITOR_ID:
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data="confirm_clear_viewed")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="cancel_clear")]
    ])
    
    await callback.message.answer("⚠️ Удалить все просмотренные домашние задания?", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "confirm_clear_viewed")
async def confirm_clear_viewed(callback: CallbackQuery):
    if callback.from_user.id != REPETITOR_ID:
        return
    
    cursor.execute("SELECT COUNT(*) FROM homework WHERE status = 'viewed'")
    count = cursor.fetchone()[0]
    
    cursor.execute("DELETE FROM homework WHERE status = 'viewed'")
    conn.commit()
    
    await callback.message.edit_text(f"✅ Удалено {count} просмотренных домашних заданий.")
    await callback.answer()

# Удаление всех
@dp.callback_query(F.data == "clear_all")
async def clear_all(callback: CallbackQuery):
    if callback.from_user.id != REPETITOR_ID:
        return
    
    cursor.execute("SELECT COUNT(*) FROM homework")
    total = cursor.fetchone()[0]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ ДА, УДАЛИТЬ ВСЁ", callback_data="confirm_clear_all")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="cancel_clear")]
    ])
    
    await callback.message.answer(f"🚨 Удалить ВСЕ домашние задания ({total} шт.)?", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "confirm_clear_all")
async def confirm_clear_all(callback: CallbackQuery):
    if callback.from_user.id != REPETITOR_ID:
        return
    
    cursor.execute("SELECT COUNT(*) FROM homework")
    count = cursor.fetchone()[0]
    
    cursor.execute("DELETE FROM homework")
    conn.commit()
    
    await callback.message.edit_text(f"⚠️ Удалено ВСЕХ домашних заданий: {count} шт.")
    await callback.answer()

@dp.callback_query(F.data == "cancel_clear")
async def cancel_clear(callback: CallbackQuery):
    await callback.message.edit_text("❌ Удаление отменено.")
    await callback.answer()

# Резервная копия
@dp.callback_query(F.data == "backup")
async def backup_db(callback: CallbackQuery):
    if callback.from_user.id != REPETITOR_ID:
        return
    
    try:
        backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2("tutor_bot.db", backup_name)
        
        await callback.message.answer_document(
            FSInputFile(backup_name),
            caption=f"💾 Резервная копия от {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
        
        os.remove(backup_name)
        await callback.message.answer("✅ Резервная копия создана!")
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")
    
    await callback.answer()

# ========== ОБРАБОТКА ФОТО ОТ УЧЕНИКА ==========

@dp.message(F.photo)
async def handle_student_photo(message: Message):
    user_id = message.from_user.id
    
    if user_id == REPETITOR_ID:
        return
    
    cursor.execute("SELECT student_name FROM students WHERE user_id = ?", (user_id,))
    student = cursor.fetchone()
    
    if student:
        photo_id = message.photo[-1].file_id
        caption = message.caption or ""
        
        # Сохраняем в БД
        cursor.execute("""
            INSERT INTO homework (student_id, teacher_id, photo_id, caption, status)
            VALUES (?, ?, ?, ?, 'new')
        """, (user_id, REPETITOR_ID, photo_id, caption))
        conn.commit()
        hw_id = cursor.lastrowid
        
        await message.answer("✅ Домашнее задание отправлено репетитору!")
        
        student_name = student[0]
        
        # Отправляем репетитору с кнопками
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отмечено", callback_data=f"mark_{hw_id}"),
                InlineKeyboardButton(text="📝 Ответить", callback_data=f"reply_{hw_id}")
            ]
        ])
        
        await bot.send_message(
            REPETITOR_ID,
            f"📸 *Новое домашнее задание!*\n\n👤 Ученик: {student_name}\n🆔 ID: `{user_id}`\n📝 {caption if caption else 'Нет комментария'}",
            parse_mode="Markdown"
        )
        await bot.send_photo(REPETITOR_ID, photo_id, reply_markup=keyboard)
    else:
        await message.answer("❌ Вы не зарегистрированы! Используйте /register")

# ========== ЗАПУСК ==========

async def main():
    print("🤖 Бот запущен!")
    print(f"📊 Репетитор ID: {REPETITOR_ID}")
    print("=" * 40)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
