import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton,
                          ReplyKeyboardMarkup, KeyboardButton, CallbackQuery)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import asyncio
import os

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get('TOKEN', "ВАШ_ТОКЕН_СЮДА")
REPETITOR_ID = int(os.environ.get('REPETITOR_ID', "123456789"))
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
    status TEXT DEFAULT 'new'
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

class TeacherSendPhoto(StatesGroup):
    waiting_for_student_id = State()

# ========== КЛАВИАТУРЫ ==========

# Главное меню для ученика/родителя
def student_keyboard():
    buttons = [
        [KeyboardButton(text="📅 Расписание")],
        [KeyboardButton(text="💰 Мой баланс")],
        [KeyboardButton(text="📤 Отправить домашку")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# Главное меню для репетитора
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
    
    # Проверяем, есть ли пользователь в БД
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
            "Пожалуйста, зарегистрируйтесь, отправив команду:\n"
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
        
        # Уведомляем репетитора
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
    paid, completed, name = cursor.fetchone()
    left = paid - completed
    
    await message.answer(
        f"💰 Баланс занятий для {name}\n\n"
        f"✅ Оплачено: {paid}\n"
        f"📚 Проведено: {completed}\n"
        f"📈 Осталось: {left}\n\n"
        f"💡 Когда остаток станет 0, вы получите напоминание об оплате."
    )

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
        "📖 Справка по боту:\n\n"
        "📅 Расписание - посмотреть расписание занятий\n"
        "💰 Мой баланс - проверить остаток занятий\n"
        "📤 Отправить домашку - отправить фото ДЗ\n\n"
        "По всем вопросам пишите репетитору."
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
    
    await message.answer(
        "➕ Добавление нового ученика\n\n"
        "Введите ФИО родителя/ученика:"
    )
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
        [InlineKeyboardButton(text="📊 Посмотреть баланс ученика", callback_data="check_balance")]
    ])
    
    await message.answer("📝 Управление занятиями:\n\nВыберите действие:", reply_markup=keyboard)

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
        text = f"📸 Домашнее задание от {student_name}\n🕐 {timestamp}\n"
        if caption:
            text += f"📝 {caption}\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отмечено", callback_data=f"mark_hw_{hw_id}"),
             InlineKeyboardButton(text="📝 Ответить", callback_data=f"reply_to_{student_name}_{hw_id}")]
        ])
        
        await bot.send_photo(REPETITOR_ID, photo_id, caption=text, reply_markup=keyboard)

@dp.message(F.text == "🔧 Настройки")
async def settings(message: Message):
    if message.from_user.id != REPETITOR_ID:
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="🗑 Очистить старые домашки", callback_data="clear_hw")]
    ])
    
    await message.answer("🔧 Настройки бота:", reply_markup=keyboard)

# ========== CALLBACK HANDLERS ==========

@dp.callback_query(F.data == "add_payment")
async def callback_add_payment(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID ученика (можно посмотреть в списке учеников):")
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
            await message.answer("❌ Ученик с таким ID не найден!")
            await state.clear()
    except:
        await message.answer("❌ ID должен быть числом!")
        await state.clear()

@dp.message(AddPayment.waiting_for_amount)
async def process_payment_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
        data = await state.get_data()
        student_id = data['student_id']
        
        cursor.execute("UPDATE students SET paid_lessons = paid_lessons + ? WHERE user_id = ?", 
                      (amount, student_id))
        cursor.execute("INSERT INTO payments (student_id, amount) VALUES (?, ?)", 
                      (student_id, amount))
        conn.commit()
        
        cursor.execute("SELECT student_name FROM students WHERE user_id = ?", (student_id,))
        student_name = cursor.fetchone()[0]
        
        await message.answer(f"✅ Добавлено {amount} занятий для {student_name}")
        
        # Уведомляем ученика
        try:
            await bot.send_message(
                student_id,
                f"💰 Пополнение баланса!\n\n"
                f"Добавлено {amount} занятий."
            )
        except:
            pass
        
        await state.clear()
    except:
        await message.answer("❌ Количество должно быть числом!")
        await state.clear()

@dp.callback_query(F.data == "complete_lesson")
async def callback_complete_lesson(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID ученика:")
    await state.set_state(CompleteLesson.waiting_for_student_id)
    await callback.answer()

@dp.message(CompleteLesson.waiting_for_student_id)
async def process_complete_lesson(message: Message, state: FSMContext):
    try:
        student_id = int(message.text)
        cursor.execute("SELECT student_name, paid_lessons, completed_lessons FROM students WHERE user_id = ?", 
                      (student_id,))
        student = cursor.fetchone()
        
        if student:
            student_name, paid, completed = student
            new_completed = completed + 1
            left = paid - new_completed
            
            cursor.execute("UPDATE students SET completed_lessons = completed_lessons + 1 WHERE user_id = ?", 
                          (student_id,))
            conn.commit()
            
            await message.answer(f"✅ Отмечено занятие для {student_name}\n"
                               f"Осталось оплаченных занятий: {left}")
            
            # Уведомляем ученика
            try:
                await bot.send_message(
                    student_id,
                    f"📚 Проведено занятие!\n\n"
                    f"Осталось оплаченных занятий: {left}"
                )
            except:
                pass
            
            # Проверяем, нужно ли напомнить об оплате
            if left <= 0:
                await bot.send_message(
                    student_id,
                    "⚠️ ВНИМАНИЕ! У вас закончились оплаченные занятия.\n\n"
                    "Пожалуйста, пополните баланс, чтобы продолжить занятия."
                )
                await message.answer(f"📢 Напоминание об оплате отправлено ученику {student_name}")
            
            await state.clear()
        else:
            await message.answer("❌ Ученик не найден!")
            await state.clear()
    except:
        await message.answer("❌ ID должен быть числом!")
        await state.clear()

@dp.callback_query(F.data == "set_schedule")
async def callback_set_schedule(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID ученика:")
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
            await message.answer(f"Ученик: {student[0]}\n\n"
                               "Введите расписание в формате:\n"
                               "Понедельник 16:00, Среда 18:30")
            await state.set_state(SetSchedule.waiting_for_schedule)
        else:
            await message.answer("❌ Ученик не найден!")
            await state.clear()
    except:
        await message.answer("❌ ID должен быть числом!")
        await state.clear()

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
    
    # Отправляем ученику
    try:
        await bot.send_message(
            student_id,
            f"📅 Репетитор установил расписание:\n\n{schedule}"
        )
    except:
        pass
    
    await state.clear()

@dp.callback_query(F.data == "check_balance")
async def callback_check_balance(callback: CallbackQuery):
    await callback.message.answer("Введите ID ученика для просмотра баланса:")
    await callback.answer()

@dp.message(F.text)
async def check_balance_by_id(message: Message):
    if message.from_user.id != REPETITOR_ID:
        return
    try:
        student_id = int(message.text)
        cursor.execute("SELECT student_name, paid_lessons, completed_lessons FROM students WHERE user_id = ?", (student_id,))
        student = cursor.fetchone()
        if student:
            student_name, paid, completed = student
            left = paid - completed
            await message.answer(f"📊 Баланс ученика {student_name}:\n\nОплачено: {paid}\nПроведено: {completed}\nОсталось: {left}")
        else:
            await message.answer("❌ Ученик не найден")
    except:
        pass

# ========== ОБРАБОТЧИКИ ДЛЯ КНОПОК ДОМАШЕК ==========

@dp.callback_query(F.data.startswith("reply_to_"))
async def reply_to_homework(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != REPETITOR_ID:
        await callback.answer("❌ Эта кнопка только для репетитора", show_alert=True)
        return
    
    # Извлекаем имя ученика и ID из callback_data
    parts = callback.data.split("_")
    student_name = parts[2]
    hw_id = int(parts[3]) if len(parts) > 3 else None
    
    # Находим ID ученика по имени
    cursor.execute("SELECT user_id FROM students WHERE student_name = ?", (student_name,))
    result = cursor.fetchone()
    
    if result:
        student_id = result[0]
        await state.update_data(reply_to_student=student_id)
        await state.set_state(ReplyToHomework.waiting_for_photo)
        
        await callback.message.answer(
            f"✍️ Отправьте ответное фото или текст для ученика {student_name}\n\n"
            f"Чтобы отменить ответ, отправьте /cancel"
        )
    else:
        await callback.message.answer("❌ Ученик не найден")
    
    await callback.answer()

@dp.callback_query(F.data.startswith("mark_hw_"))
async def mark_homework_done(callback: CallbackQuery):
    if callback.from_user.id != REPETITOR_ID:
        await callback.answer("❌ Только для репетитора", show_alert=True)
        return
    
    hw_id = int(callback.data.split("_")[2])
    
    cursor.execute("UPDATE homework SET status = 'viewed' WHERE id = ?", (hw_id,))
    conn.commit()
    
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("✅ Домашнее задание отмечено как просмотренное")

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
        f"📊 *Статистика бота*\n\n"
        f"👥 Учеников: {students_count}\n"
        f"✅ Всего оплачено занятий: {total_paid}\n"
        f"📚 Всего проведено занятий: {total_completed}\n"
        f"📸 Ожидают проверки домашек: {pending_hw}",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "clear_hw")
async def clear_old_hw(callback: CallbackQuery):
    if callback.from_user.id != REPETITOR_ID:
        return
    
    cursor.execute("DELETE FROM homework WHERE status = 'viewed'")
    conn.commit()
    
    await callback.message.answer("✅ Старые просмотренные домашки удалены")
    await callback.answer()

# ========== ОБРАБОТКА ФОТО (ДОМАШКА) ==========

@dp.message(ReplyToHomework.waiting_for_photo, F.photo)
async def send_reply_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    student_id = data.get('reply_to_student')
    
    if not student_id:
        await message.answer("❌ Ошибка: не найден ученик для ответа")
        await state.clear()
        return
    
    photo_id = message.photo[-1].file_id
    caption = message.caption or "📝 Ответ на домашнее задание"
    
    try:
        await bot.send_photo(
            student_id,
            photo_id,
            caption=f"📢 Ответ от репетитора:\n\n{caption}"
        )
        await message.answer(f"✅ Ответ отправлен ученику!")
        
        cursor.execute("""
            INSERT INTO homework (student_id, teacher_id, photo_id, caption, status)
            VALUES (?, ?, ?, ?, 'reply')
        """, (student_id, REPETITOR_ID, photo_id, caption))
        conn.commit()
        
    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке: {e}")
    
    await state.clear()

@dp.message(ReplyToHomework.waiting_for_photo, F.text)
async def send_reply_text(message: Message, state: FSMContext):
    data = await state.get_data()
    student_id = data.get('reply_to_student')
    
    if not student_id:
        await message.answer("❌ Ошибка: не найден ученик для ответа")
        await state.clear()
        return
    
    try:
        await bot.send_message(
            student_id,
            f"📢 Ответ от репетитора:\n\n{message.text}"
        )
        await message.answer(f"✅ Ответ отправлен ученику!")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(F.photo)
async def handle_homework_photo(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    cursor.execute("SELECT student_name FROM students WHERE user_id = ?", (user_id,))
    student = cursor.fetchone()
    
    if user_id == REPETITOR_ID:
        # Репетитор отправил фото — спрашиваем, кому
        await message.answer("Кому отправить это фото? Введите ID ученика или имя ученика\n\nДля отмены: /cancel")
        await state.update_data(pending_photo=message.photo[-1].file_id, pending_caption=message.caption or "")
        await state.set_state(TeacherSendPhoto.waiting_for_student_id)
        
    elif student:
        # Ученик отправил — сохраняем и уведомляем репетитора
        photo_id = message.photo[-1].file_id
        caption = message.caption or ""
        
        cursor.execute("""
            INSERT INTO homework (student_id, teacher_id, photo_id, caption, status)
            VALUES (?, ?, ?, ?, 'new')
        """, (user_id, REPETITOR_ID, photo_id, caption))
        conn.commit()
        hw_id = cursor.lastrowid
        
        await message.answer("✅ Домашнее задание отправлено репетитору!")
        
        # Получаем имя ученика
        student_name = student[0]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Ответить", callback_data=f"reply_to_{student_name}_{hw_id}")]
        ])
        
        await bot.send_message(
            REPETITOR_ID,
            f"📸 Новое домашнее задание от {student_name}!\n"
            f"ID ученика: `{user_id}`\n"
            f"Комментарий: {caption if caption else 'Нет комментария'}"
        )
        await bot.send_photo(REPETITOR_ID, photo_id, reply_markup=keyboard)
    else:
        await message.answer("❌ Вы не зарегистрированы! Используйте /register")

@dp.message(TeacherSendPhoto.waiting_for_student_id, F.text)
async def process_teacher_send_photo(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отправка отменена")
        return
    
    try:
        # Пробуем найти по ID или по имени
        student_id = None
        if message.text.isdigit():
            student_id = int(message.text)
            cursor.execute("SELECT student_name FROM students WHERE user_id = ?", (student_id,))
        else:
            cursor.execute("SELECT user_id, student_name FROM students WHERE student_name LIKE ?", (f"%{message.text}%",))
        
        student = cursor.fetchone()
        
        if student:
            student_id = student[0] if isinstance(student, tuple) and len(student) > 0 else student_id
            student_name = student[1] if len(student) > 1 else message.text
            
            data = await state.get_data()
            photo_id = data.get('pending_photo')
            caption = data.get('pending_caption', '')
            
            await bot.send_photo(
                student_id,
                photo_id,
                caption=f"📚 Материал от репетитора:\n\n{caption}"
            )
            await message.answer(f"✅ Фото отправлено ученику {student_name}")
            await state.clear()
        else:
            await message.answer("❌ Ученик с таким ID/именем не найден!\n\nВведите ID из списка учеников (команда /start → Все ученики)")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ========== ЗАПУСК ==========

async def main():
    print("🤖 Бот запущен!")
    print(f"📊 Репетитор ID: {REPETITOR_ID}")
    print("=" * 40)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
