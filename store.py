import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, timedelta

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
  
  # Конфигурация
BOT_TOKEN = "8458815596:AAHzIGc9CKWaxs_vIwm8nBq1yfKuzYIVsLw"
OWNER_ID = 1492555556

# Категории товаров
CATEGORIES = ["Поды", "Жижа", "Снюс", "Луп", "Испарители"]

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    
    # Таблица товаров
    cursor.execute('''
        DROP TABLE IF EXISTS products
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            photo TEXT,
            category TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица вариаций товаров
    cursor.execute('''
        DROP TABLE IF EXISTS product_variations
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_variations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            attribute_name TEXT NOT NULL,
            attribute_value TEXT NOT NULL,
            stock INTEGER DEFAULT 0,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        )
    ''')
    
    # Удаляем старую таблицу orders, если она существует, чтобы обновить схему
    cursor.execute('DROP TABLE IF EXISTS orders')
    
    # Таблица заказов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            product_variation_id INTEGER NOT NULL,
            product_name TEXT,
            variation_name TEXT,
            quantity INTEGER NOT NULL,
            total_price REAL NOT NULL,
            payment_method TEXT,
            comment TEXT,
            status TEXT DEFAULT 'new',
            pickup_status TEXT DEFAULT 'not_arrived',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_variation_id) REFERENCES product_variations (id) ON DELETE CASCADE
        )
    ''')
    
    # Удаляем старую таблицу settings, если она существует, чтобы обновить схему
    cursor.execute('DROP TABLE IF EXISTS settings')
    
    # Таблица настроек
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            start_hour INTEGER DEFAULT 9,
            end_hour INTEGER DEFAULT 20
        )
    ''')
    
    cursor.execute('''
        INSERT OR IGNORE INTO settings (key, value) 
        VALUES ('shop_address', 'Адрес не установлен')
    ''')
    
    cursor.execute('''
        INSERT OR IGNORE INTO settings (key, value, start_hour, end_hour)
        VALUES ('working_hours', 'Рабочие часы', 9, 20)
    ''')
    
    conn.commit()
    conn.close()

# Функции для работы с настройками
def get_shop_address():
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'shop_address'")
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "Адрес не установлен"

def set_shop_address(address):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO settings (key, value) 
        VALUES ('shop_address', ?)
    ''', (address,))
    conn.commit()
    conn.close()

# Клавиатуры
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🛍️ Каталог товаров"), KeyboardButton("🛒 Мои заказы")],
        [KeyboardButton("📞 Контакты"), KeyboardButton("ℹ️ О нас")]
    ], resize_keyboard=True)

def get_owner_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📦 Управление товарами"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("📋 Заказы"), KeyboardButton("🏪 Установить адрес")],
        [KeyboardButton("🧹 Очистить данные бота"), KeyboardButton("🏠 Главное меню")]
    ], resize_keyboard=True)

def get_products_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ Добавить товар"), KeyboardButton("📋 Список товаров")],
        [KeyboardButton("📦 Управление вариациями"), KeyboardButton("⬅️ Назад")]
    ], resize_keyboard=True)

def get_payment_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 Наличные", callback_data="payment_cash")],
        [InlineKeyboardButton("💳 Перевод", callback_data="payment_transfer")],
        [InlineKeyboardButton("❌ Отмена", callback_data="payment_cancel")]
    ])

def get_comment_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("⏭️ Пропустить комментарий")],
        [KeyboardButton("❌ Отмена заказа")]
    ], resize_keyboard=True)

def get_confirm_clear_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, очистить", callback_data="clear_confirm")],
        [InlineKeyboardButton("❌ Нет, отмена", callback_data="clear_cancel")]
    ])

def get_edit_product_photo_keyboard(product_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬆️ Загрузить новое фото", callback_data=f"upload_new_product_photo_{product_id}")],
        [InlineKeyboardButton("🗑️ Удалить текущее фото", callback_data=f"remove_product_photo_{product_id}")],
        [InlineKeyboardButton("⬅️ Назад к списку товаров", callback_data="back_to_list_products")]
    ])

def get_category_selection_keyboard():
    keyboard = []
    for category in CATEGORIES:
        keyboard.append([InlineKeyboardButton(category, callback_data=f"add_product_category_{category}")])
    keyboard.append([InlineKeyboardButton("❌ Отмена добавления", callback_data="add_product_cancel")])
    return InlineKeyboardMarkup(keyboard)

def get_product_variations_for_user_keyboard(product_id, variations):
    keyboard = []
    for variation_id, attribute_name, attribute_value, stock in variations:
        if stock > 0:
            button_text = f"{attribute_name}: {attribute_value} (В наличии: {stock} шт.)"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"select_variation_for_purchase_{variation_id}")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад к товарам", callback_data=f"back_to_products_in_category_{product_id}")])
    return InlineKeyboardMarkup(keyboard)


async def clear_bot_data(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM orders")
    cursor.execute("DELETE FROM products")
    cursor.execute("DELETE FROM product_variations")
    conn.commit()
    conn.close()
    
    # Очищаем также pending_pickups из bot_data
    if 'pending_pickups' in context.application.bot_data:
        context.application.bot_data['pending_pickups'] = {}
    
    # Отменяем все активные напоминания
    for job in context.job_queue.get_jobs_by_name(f"pickup_reminder_"):
        job.schedule_removal()

def get_manage_stock_keyboard(product_id, current_stock):
    keyboard = [
        [InlineKeyboardButton("➖", callback_data=f"manage_stock_decrease_{product_id}"),
         InlineKeyboardButton(f"В наличии: {current_stock}", callback_data="_ignore"),
         InlineKeyboardButton("➕", callback_data=f"manage_stock_increase_{product_id}")],
        [InlineKeyboardButton("📝 Ввести количество", callback_data=f"manage_stock_input_{product_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_manage_products")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_manage_variations_keyboard(product_id, variations):
    keyboard = []
    for variation_id, attribute_name, attribute_value, stock in variations:
        keyboard.append([InlineKeyboardButton(f"{attribute_name}: {attribute_value} (В наличии: {stock} шт.)", callback_data=f"edit_variation_{variation_id}")])
    keyboard.append([InlineKeyboardButton("➕ Добавить вариацию", callback_data=f"add_variation_to_product_{product_id}")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад к списку товаров", callback_data="back_to_manage_products_list")])
    return InlineKeyboardMarkup(keyboard)


async def send_manage_products_for_variations(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id=None):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, category FROM products ORDER BY category, name")
    products = cursor.fetchall()
    conn.close()

    if not products:
        if message_id:
            await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=message_id, text="📦 Товаров пока нет для управления вариациями.")
        else:
            await update.message.reply_text("📦 Товаров пока нет для управления вариациями.")
        return

    keyboard = []
    for product_id, name, category in products:
        keyboard.append([InlineKeyboardButton(f"📦 {name} (Категория: {category or 'Без категории'})", callback_data=f"select_product_for_variations_{product_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад к управлению товарами", callback_data="back_to_products_management")])

    message_text = "📊 Выберите товар для управления вариациями:"
    if message_id:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=message_id, text=message_text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def send_manage_variations_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id, product_id):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, attribute_name, attribute_value, stock FROM product_variations WHERE product_id = ?", (product_id,))
    variations = cursor.fetchall()
    cursor.execute("SELECT name FROM products WHERE id = ?", (product_id,))
    product_name = cursor.fetchone()[0]
    conn.close()

    keyboard = get_manage_variations_keyboard(product_id, variations)

    message_text = f"📦 Вариации для товара '{product_name}' (ID: {product_id}):"
    if not variations:
        message_text += "\n\nПока нет вариаций для этого товара."

    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=message_id, text=message_text, reply_markup=keyboard)

def get_pickup_keyboard(order_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚶 Идти за товаром", callback_data=f"pickup_go_{order_id}")],
        [InlineKeyboardButton("⏰ Приду попозже", callback_data=f"pickup_later_{order_id}")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
    ])

def get_arrival_keyboard(order_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Я на месте", callback_data=f"arrived_{order_id}")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
    ])

def get_admin_order_actions_keyboard(order_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚶 Выхожу с товаром", callback_data=f"admin_confirm_pickup_{order_id}")],
        [InlineKeyboardButton("❌ Отменить заказ", callback_data=f"admin_cancel_order_{order_id}")]
    ])

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    
    if user.id == OWNER_ID:
        await update.message.reply_text(
            "👑 Добро пожаловать в панель администратора!",
            reply_markup=get_owner_keyboard()
        )
    else:
        welcome_text = f"""👋 Добро пожаловать, {user.first_name}!

В нашем магазине вы найдете лучшие товары по выгодным ценам!

📋 Используйте кнопки ниже для навигации:
• 🛍️ Каталог - просмотр товаров
• 🛒 Мои заказы - история покупок
• 📞 Контакты - связь с нами"""
        await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

# Каталог товаров
def get_catalog_keyboard():
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT p.category FROM products p JOIN product_variations pv ON p.id = pv.product_id WHERE pv.stock > 0 AND p.category IS NOT NULL")
    categories_with_products = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    logger.info(f"Categories with products from DB: {categories_with_products}")

    keyboard = []
    for category in CATEGORIES:
        if category in categories_with_products:
            keyboard.append([InlineKeyboardButton(f"📂 {category}", callback_data=f"catalog_{category}")])
    
    logger.info(f"Generated catalog keyboard: {keyboard}")
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM products") # Проверяем наличие товаров в целом
    count = cursor.fetchone()[0]
    conn.close()
    
    logger.info(f"Total products in DB: {count}")

    if count == 0:
        await update.message.reply_text("😔 В настоящее время товаров нет в наличии.")
        return
    
    catalog_keyboard = get_catalog_keyboard()
    logger.info(f"Catalog keyboard from get_catalog_keyboard: {catalog_keyboard}")

    await update.message.reply_text(
        "🛍️ Выберите категорию товаров:",
        reply_markup=catalog_keyboard
    )

# Управление товарами
async def manage_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != OWNER_ID:
        await update.message.reply_text("⛔ У вас нет доступа к этой команде.")
        return
    
    await update.message.reply_text(
        "📦 Управление товарами\n\nВыберите действие:",
        reply_markup=get_products_keyboard()
    )

async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != OWNER_ID:
        await update.message.reply_text("⛔ У вас нет доступа к этой команде.")
        return
    
    context.user_data['awaiting_product_category'] = True
    await update.message.reply_text(
        "📦 Выберите категорию для добавления товара:",
        reply_markup=get_category_selection_keyboard()
    )

async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != OWNER_ID:
        await update.message.reply_text("⛔ У вас нет доступа к этой команде.")
        return
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products ORDER BY category, id")
    products = cursor.fetchall()
    conn.close()
    
    if not products:
        await update.message.reply_text("📦 Товаров пока нет.")
        return
    
    for product in products:
        product_id, name, description, price, photo, category, created_at = product
        
        message_text = f"""📦 Товар #{product_id}
🏷️ Название: {name}
📝 Описание: {description}
💵 Цена: {price} руб.
📂 Категория: {category or 'Без категории'}"""

        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(stock) FROM product_variations WHERE product_id = ?", (product_id,))
        total_stock = cursor.fetchone()[0] or 0
        conn.close()
        message_text += f"\n📦 Общий остаток: {total_stock} шт."
        
        keyboard = [
            [
                InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{product_id}"),
                InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{product_id}"),
                InlineKeyboardButton("📸 Фото", callback_data=f"edit_product_photo_{product_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if photo:
            await update.message.reply_photo(
                photo=photo,
                caption=message_text,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup)

# Обработка callback-запросов
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user

    logger.info(f"Received callback_data: {data} (Type: {type(data)})")

    if not isinstance(data, str):
        logger.error(f"Invalid callback_data type: {type(data)}. Data: {data}")
        await query.message.reply_text("❌ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте еще раз.")
        return

    if data == 'back_to_main':
        if user.id == OWNER_ID:
            await query.message.reply_text("👑 Панель администратора", reply_markup=get_owner_keyboard())
        else:
            await query.message.reply_text("🏠 Главное меню", reply_markup=get_main_keyboard())
    
    elif data.startswith('catalog_'):
        category = data.replace('catalog_', '')
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT p.id, p.name, p.price, p.photo, SUM(pv.stock) FROM products p JOIN product_variations pv ON p.id = pv.product_id WHERE p.category = ? GROUP BY p.id HAVING SUM(pv.stock) > 0 ORDER BY p.id", (category,))
        products = cursor.fetchall()
        
        if not products:
            conn.close()
            await query.message.reply_text(f"😔 В категории '{category}' товаров нет в наличии.")
            return
        
        keyboard = []
        for product_id, name, price, photo, total_stock in products:
            button_text = f"{name} - {price}₽ ({total_stock} шт.)"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"buy_{product_id}")])
        
        keyboard.append([InlineKeyboardButton("⬅️ Назад к категориям", callback_data="back_to_catalog")])
        
        # Получаем фотографию первого товара в категории, если есть
        first_product_photo = None
        for product in products:
            if product[3]: # product[3] это photo (индекс изменился)
                first_product_photo = product[3]
                break
        
        conn.close() # Закрываем соединение после всех операций с БД

        message_text = f"📂 {category}\n\nВыберите товар:"

        if first_product_photo:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=first_product_photo,
                caption=message_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.message.reply_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    elif data == 'back_to_catalog':
        await query.message.reply_text(
            "🛍️ Выберите категорию товаров:",
            reply_markup=get_catalog_keyboard()
        )
    
    elif data.startswith('buy_'):
        product_id = int(data.split('_')[1])
        
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name, description, price, photo FROM products WHERE id = ?", (product_id,))
        product = cursor.fetchone()
        cursor.execute("SELECT id, attribute_name, attribute_value, stock FROM product_variations WHERE product_id = ? AND stock > 0", (product_id,))
        variations = cursor.fetchall()
        conn.close()
        
        if not product:
            await query.message.reply_text("❌ Товар не найден.")
            return
        
        product_name, description, price, photo = product

        if not variations:
            await query.message.reply_text(f"❌ Извините, у товара '{product_name}' нет доступных вариаций.")
            return

        message_text = f"🛒 Вы выбрали: {product_name}\n\nВыберите вариацию:"

        if photo:
            sent_message = await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=photo,
                caption=message_text,
                reply_markup=get_product_variations_for_user_keyboard(product_id, variations)
            )
        else:
            sent_message = await query.message.reply_text(message_text, reply_markup=get_product_variations_for_user_keyboard(product_id, variations))
        
        context.user_data['variation_selection_message_id'] = sent_message.message_id

    elif data.startswith('select_variation_for_purchase_'):
        variation_id = int(data.replace('select_variation_for_purchase_', ''))

        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT pv.product_id, pv.attribute_name, pv.attribute_value, pv.stock, p.name, p.price FROM product_variations pv JOIN products p ON pv.product_id = p.id WHERE pv.id = ?", (variation_id,))
        variation_data = cursor.fetchone()
        conn.close()

        if not variation_data:
            await query.message.reply_text("❌ Вариация не найдена.")
            return
        
        product_id, attribute_name, attribute_value, stock, product_name, base_price = variation_data

        if stock <= 0:
            await query.message.reply_text(f"❌ Извините, вариация '{attribute_name}: {attribute_value}' временно отсутствует в наличии.")
            return
        
        # Сохраняем данные о заказе
        context.user_data['current_order'] = {
            'product_id': product_id, # Это ID основного продукта
            'product_name': product_name,
            'variation_id': variation_id,
            'variation_name': f"{attribute_name}: {attribute_value}",
            'price': base_price # Цена основного продукта, вариации могут иметь свою цену позже
        }

        logger.info(f"User {user.id} selected variation. Current order data: {context.user_data['current_order']}")

        product_info = f"""🛒 Вы выбрали:

📦 Товар: {product_name}
🎨 Вариация: {attribute_name}: {attribute_value}
💵 Цена: {base_price} руб.
📦 В наличии: {stock} шт.

Выберите способ оплаты:"""

        message_id_to_edit = context.user_data.pop('variation_selection_message_id', None)

        if message_id_to_edit:
            await context.bot.edit_message_caption(
                chat_id=query.message.chat_id,
                message_id=message_id_to_edit,
                caption=product_info,
                reply_markup=get_payment_keyboard()
            )
        else:
            # Fallback: если по какой-то причине message_id_to_edit отсутствует, отправляем новое сообщение
            await query.message.reply_text(product_info, reply_markup=get_payment_keyboard())

    elif data.startswith('back_to_products_in_category_'):
        product_id = int(data.replace('back_to_products_in_category_', ''))
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT category FROM products WHERE id = ?", (product_id,))
        category = cursor.fetchone()[0]
        conn.close()
        await query.message.reply_text(
            f"📂 {category}\n\nВыберите товар:",
            reply_markup=get_catalog_keyboard()
        )
    
    elif data in ['payment_cash', 'payment_transfer']:
        logger.info(f"User {user.id} chose payment method. Current user data: {context.user_data}")
        if 'current_order' not in context.user_data:
            await query.message.reply_text("❌ Ошибка: данные заказа не найдены.")
            return
            
        payment_method = 'наличные' if data == 'payment_cash' else 'перевод'
        context.user_data['current_order']['payment_method'] = payment_method
        context.user_data['awaiting_comment'] = True
        
        await query.message.reply_text(
            f"💳 Способ оплаты: {payment_method}\n\n"
            f"💬 Хотите добавить комментарий к заказу?\n"
            f"Например: вкус апельсин, сильный хит и т.д.\n\n"
            f"Напишите комментарий или нажмите 'Пропустить комментарий':",
            reply_markup=get_comment_keyboard()
        )
    
    elif data == 'payment_cancel':
        context.user_data.pop('current_order', None)
        context.user_data.pop('awaiting_comment', None)
        await query.message.reply_text("❌ Покупка отменена.")
        await query.message.reply_text(
            "🛍️ Выберите категорию товаров:",
            reply_markup=get_catalog_keyboard()
        )
    
    elif data.startswith('pickup_go_'):
        order_id = int(data.split('_')[2])
        await query.message.reply_text(
            f"🚶 Отлично! Вы идете за товаром.\n\n"
            f"🏪 Адрес магазина:\n{get_shop_address()}\n\n"
            f"Когда придете на место, нажмите кнопку ниже:",
            reply_markup=get_arrival_keyboard(order_id)
        )
    
    elif data.startswith('pickup_later_'):
        order_id = int(data.split('_')[2])
        await query.message.reply_text(
            f"⏰ Хорошо, ждем вас позже!\n\n"
            f"🏪 Адрес магазина:\n{get_shop_address()}\n\n"
            f"Не забудьте забрать ваш заказ №{order_id}",
            reply_markup=get_main_keyboard()
        )
    
    elif data.startswith('arrived_'):
        order_id = int(data.split('_')[1])
        user = query.from_user
        
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET pickup_status = 'arrived' WHERE id = ?", (order_id,))
        cursor.execute("SELECT product_name, total_price, user_id, user_name FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        conn.commit()
        conn.close()
        
        if order:
            product_name, total_price, customer_user_id, customer_user_name = order
            
            await query.message.reply_text(
                f"✅ Отлично! Мы вас ждем.\n\n"
                f"📦 Заказ: {product_name}\n"
                f"💵 Сумма: {total_price} руб.\n"
                f"🆔 Номер: {order_id}\n\n"
                f"Скоро подойдем к вам!",
                reply_markup=get_main_keyboard()
            )

            # Оповещение администратора
            admin_alert_message = f"""🚨 ПОКУПАТЕЛЬ НА МЕСТЕ! 🚨

👤 Покупатель: {customer_user_name} (ID: {customer_user_id})
📦 Заказ: {product_name}
💵 Сумма: {total_price} руб.
🆔 Номер заказа: {order_id}

Нажмите 'Выхожу с товаром', когда будете готовы."""

            admin_message = await context.bot.send_message(
                chat_id=OWNER_ID,
                text=admin_alert_message,
                reply_markup=get_admin_order_actions_keyboard(order_id)
            )
            if 'pending_pickups' not in context.application.bot_data:
                context.application.bot_data['pending_pickups'] = {}
            
            context.application.bot_data['pending_pickups'][order_id] = {
                'customer_id': customer_user_id,
                'admin_message_id': admin_message.message_id,
                'last_reminder_time': datetime.now()
            }
            # Запланировать напоминание через 30 секунд
            context.job_queue.run_once(send_pickup_reminder, 30, data=order_id, name=f"pickup_reminder_{order_id}")

    elif data.startswith('admin_confirm_pickup_'):
        order_id = int(data.split('_')[3])
        
        if 'pending_pickups' in context.application.bot_data and order_id in context.application.bot_data['pending_pickups']:
            pickup_info = context.application.bot_data['pending_pickups'].pop(order_id) # Удаляем из списка ожидающих
            
            # Отменяем запланированные напоминания
            current_jobs = context.job_queue.get_jobs_by_name(f"pickup_reminder_{order_id}")
            for job in current_jobs:
                job.schedule_removal()
            
            conn = sqlite3.connect('shop.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE orders SET status = 'completed', pickup_status = 'picked_up' WHERE id = ?", (order_id,))
            cursor.execute("SELECT product_name, user_id FROM orders WHERE id = ?", (order_id,))
            order = cursor.fetchone()
            conn.commit()
            conn.close()
            
            if order:
                product_name, customer_user_id = order
                await query.edit_message_text(
                    text=f"✅ Заказ #{order_id} ({product_name}) подтвержден к выдаче!",
                    reply_markup=None
                )
                await context.bot.send_message(
                    chat_id=customer_user_id,
                    text=f"🎉 Ваш заказ #{order_id} ({product_name}) выдан администратором. Спасибо за покупку!",
                    reply_markup=get_main_keyboard()
                )
                logger.info(f"Администратор подтвердил выдачу заказа #{order_id}")
        else:
            await query.edit_message_text("❌ Не удалось найти информацию о заказе или он уже был обработан.", reply_markup=None)
    
    elif data.startswith('admin_cancel_order_'):
        order_id = int(data.split('_')[3])
        
        if 'pending_pickups' in context.application.bot_data and order_id in context.application.bot_data['pending_pickups']:
            pickup_info = context.application.bot_data['pending_pickups'].pop(order_id) # Удаляем из списка ожидающих
            
            # Отменяем запланированные напоминания
            current_jobs = context.job_queue.get_jobs_by_name(f"pickup_reminder_{order_id}")
            for job in current_jobs:
                job.schedule_removal()
            
            conn = sqlite3.connect('shop.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE orders SET status = 'cancelled', pickup_status = 'cancelled' WHERE id = ?", (order_id,))
            # Возвращаем товар на склад
            cursor.execute("UPDATE products SET stock = stock + 1 WHERE id = (SELECT product_id FROM orders WHERE id = ?)", (order_id,))
            cursor.execute("SELECT product_name, user_id FROM orders WHERE id = ?", (order_id,))
            order = cursor.fetchone()
            conn.commit()
            conn.close()
            
            if order:
                product_name, customer_user_id = order
                await query.edit_message_text(
                    text=f"❌ Заказ #{order_id} ({product_name}) отменен администратором.",
                    reply_markup=None
                )
                await context.bot.send_message(
                    chat_id=customer_user_id,
                    text=f"😔 Ваш заказ #{order_id} ({product_name}) был отменен администратором. Приносим извинения.",
                    reply_markup=get_main_keyboard()
                )
                logger.info(f"Администратор отменил заказ #{order_id}")
        else:
            await query.edit_message_text("❌ Не удалось найти информацию о заказе или он уже был обработан.", reply_markup=None)

    elif data == 'clear_confirm':
        if user.id != OWNER_ID:
            await query.answer("⛔ У вас нет доступа к этой команде.")
            return
        
        await clear_bot_data(context)
        await query.edit_message_text("✅ Все данные бота (заказы и товары) успешно очищены.", reply_markup=None)
        await context.bot.send_message(chat_id=OWNER_ID, text="Возвращаемся в главное меню админ-панели.", reply_markup=get_owner_keyboard())
        logger.info(f"Администратор {user.id} очистил все данные бота.")

    elif data == 'clear_cancel':
        if user.id != OWNER_ID:
            await query.answer("⛔ У вас нет доступа к этой команде.")
            return
        
        await query.edit_message_text("❌ Очистка данных отменена.", reply_markup=None)
        await context.bot.send_message(chat_id=OWNER_ID, text="Возвращаемся в главное меню админ-панели.", reply_markup=get_owner_keyboard())
        logger.info(f"Администратор {user.id} отменил очистку данных бота.")

    elif data.startswith('add_product_category_'):
        category = data.replace('add_product_category_', '')
        if category in CATEGORIES:
            context.user_data['product_category'] = category
            context.user_data['awaiting_product_category'] = False # Сбросим флаг выбора категории
            context.user_data['awaiting_product_name'] = True # Установим флаг ожидания названия товара
            await query.edit_message_text(
                f"📦 Выбрана категория: {category}.\nВведите название товара:"
            )
        else:
            await query.edit_message_text("❌ Неизвестная категория. Пожалуйста, выберите категорию из списка.", reply_markup=get_category_selection_keyboard())
            
    elif data == 'add_product_cancel':
        context.user_data.pop('awaiting_product_category', None)
        context.user_data.pop('product_category', None)
        context.user_data.pop('awaiting_product_name', None)
        context.user_data.pop('awaiting_product_price', None)
        await query.edit_message_text("📦 Отмена добавления товара.", reply_markup=None)
        await context.bot.send_message(chat_id=OWNER_ID, text="Возвращаемся в главное меню админ-панели.", reply_markup=get_owner_keyboard())
        context.user_data.clear()

    elif data.startswith('manage_product_stock_'):
        product_id = int(data.replace('manage_product_stock_', ''))
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT stock FROM products WHERE id = ?", (product_id,))
        result = cursor.fetchone()
        conn.close()

        if not result:
            await query.message.reply_text("❌ Товар не найден.")
            return

        current_stock = result[0]
        await query.message.reply_text(
            f"📊 Управление наличием для товара '{product_id}':\n\n"
            f"📦 Текущий остаток: {current_stock} шт.\n"
            f"Выберите действие:",
            reply_markup=get_manage_stock_keyboard(product_id, current_stock)
        )

    elif data.startswith('manage_stock_decrease_'):
        product_id = int(data.replace('manage_stock_decrease_', ''))
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT stock FROM products WHERE id = ?", (product_id,))
        result = cursor.fetchone()
        conn.close()

        if not result:
            await query.message.reply_text("❌ Товар не найден.")
            return

        current_stock = result[0]
        if current_stock <= 0:
            await query.message.reply_text("❌ Товар уже в минимальном остатке.")
            return

        await query.message.reply_text(
            f"📊 Управление наличием для товара '{product_id}':\n\n"
            f"📦 Текущий остаток: {current_stock} шт.\n"
            f"Вы уверены, что хотите уменьшить остаток на 1 шт.?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Да", callback_data=f"confirm_decrease_{product_id}"), InlineKeyboardButton("❌ Нет", callback_data="back_to_manage_products_list_from_stock_edit")],
                [InlineKeyboardButton("⬅️ Назад к списку товаров", callback_data="back_to_manage_products_list_from_stock_edit")]
            ])
        )

    elif data.startswith('confirm_decrease_'):
        product_id = int(data.replace('confirm_decrease_', ''))
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET stock = stock - 1 WHERE id = ?", (product_id,))
        conn.commit()
        conn.close()

        await send_manage_products_for_variations(update, context, update.callback_query.message.message_id)
        await query.message.reply_text(f"✅ Остаток товара '{product_id}' успешно уменьшен на 1 шт.")

    elif data.startswith('manage_stock_increase_'):
        product_id = int(data.replace('manage_stock_increase_', ''))
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT stock FROM products WHERE id = ?", (product_id,))
        result = cursor.fetchone()
        conn.close()

        if not result:
            await query.message.reply_text("❌ Товар не найден.")
            return

        current_stock = result[0]
        await query.message.reply_text(
            f"📊 Управление наличием для товара '{product_id}':\n\n"
            f"📦 Текущий остаток: {current_stock} шт.\n"
            f"Вы уверены, что хотите увеличить остаток на 1 шт.?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Да", callback_data=f"confirm_increase_{product_id}"), InlineKeyboardButton("❌ Нет", callback_data="back_to_manage_products_list_from_stock_edit")],
                [InlineKeyboardButton("⬅️ Назад к списку товаров", callback_data="back_to_manage_products_list_from_stock_edit")]
            ])
        )

    elif data.startswith('confirm_increase_'):
        product_id = int(data.replace('confirm_increase_', ''))
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET stock = stock + 1 WHERE id = ?", (product_id,))
        conn.commit()
        conn.close()

        await send_manage_products_for_variations(update, context, update.callback_query.message.message_id)
        await query.message.reply_text(f"✅ Остаток товара '{product_id}' успешно увеличен на 1 шт.")

    elif data == 'back_to_manage_products_list_from_stock_edit':
        await send_manage_products_for_variations(update, context, update.callback_query.message.message_id)

    elif data == 'back_to_products_management':
        await update.callback_query.message.reply_text(
            "📦 Управление товарами\n\nВыберите действие:",
            reply_markup=get_products_keyboard()
        )
    
    elif data.startswith('manage_stock_input_'):
        product_id = int(data.replace('manage_stock_input_', ''))
        context.user_data['awaiting_stock_input'] = product_id
        await query.message.reply_text("🔢 Введите новое количество товара (целое число):")
    
    elif data.startswith('edit_product_photo_'):
        product_id = int(data.replace('edit_product_photo_', ''))
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name, photo FROM products WHERE id = ?", (product_id,))
        product_name, current_photo = cursor.fetchone()
        conn.close()

        message_text = f"📸 Управление фото для товара '{product_name}' (ID: {product_id})."
        if current_photo:
            await context.bot.send_photo(
                chat_id=user.id,
                photo=current_photo,
                caption=f"Текущее фото товара '{product_name}':"
            )
        else:
            message_text += "\nТекущее фото отсутствует."

        await query.message.reply_text(message_text, reply_markup=get_edit_product_photo_keyboard(product_id))

    elif data.startswith('upload_new_product_photo_'):
        product_id = int(data.replace('upload_new_product_photo_', ''))
        context.user_data['awaiting_product_photo_edit'] = product_id
        await query.message.reply_text("⬆️ Отправьте новое фото для этого товара.")

    elif data.startswith('remove_product_photo_'):
        product_id = int(data.replace('remove_product_photo_', ''))
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET photo = NULL WHERE id = ?", (product_id,))
        conn.commit()
        conn.close()
        await query.message.reply_text("🗑️ Фото товара успешно удалено.", reply_markup=get_products_keyboard())
        await list_products(update, context) # Обновить список товаров

    elif data == 'back_to_list_products':
        await list_products(update, context)
    
    elif data.startswith('select_product_for_variations_'):
        product_id = int(data.replace('select_product_for_variations_', ''))
        await send_manage_variations_keyboard(update, context, query.message.message_id, product_id)
    
    elif data.startswith('add_variation_to_product_'):
        product_id = int(data.replace('add_variation_to_product_', ''))
        context.user_data['awaiting_new_variation_attribute_name'] = product_id
        await query.message.reply_text(f"➕ Для товара ID {product_id}: Введите название атрибута вариации (например, 'Цвет', 'Вкус'):")
    
    elif data.startswith('edit_variation_'):
        variation_id = int(data.replace('edit_variation_', ''))
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT attribute_name, attribute_value, stock FROM product_variations WHERE id = ?", (variation_id,))
        variation_name, variation_value, current_stock = cursor.fetchone()
        conn.close()
        
        context.user_data['awaiting_variation_value_and_stock_input'] = variation_id
        context.user_data['current_variation_attribute_name'] = variation_name
        
        # Получаем product_id для этой вариации, чтобы затем вернуться к управлению вариациями
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT product_id FROM product_variations WHERE id = ?", (variation_id,))
        product_id_for_variation = cursor.fetchone()[0]
        conn.close()
        context.user_data['product_id_for_variation_management'] = product_id_for_variation

        sent_message = await query.message.reply_text(
            f"📦 Вариация: {variation_name}\nТекущее значение: {variation_value}\nТекущий остаток: {current_stock} шт.\n\n"
            f"Введите новое значение атрибута и количество, разделенные пробелом (например, '{variation_value} {current_stock}'):"
        )
        context.user_data['variation_edit_message_id'] = sent_message.message_id

    elif data == 'back_to_manage_products_list':
        await send_manage_products_for_variations(update, context, query.message.message_id)

# Обработка оплаты
async def process_payment(update, context, order_data, comment=None):
    try:
        # Определяем, откуда пришло обновление (сообщение или callback)
        if hasattr(update, 'message'):
            user = update.message.from_user
            send_message_func = update.message.reply_text
        elif hasattr(update, 'callback_query'):
            user = update.callback_query.from_user
            send_message_func = update.callback_query.message.reply_text
        else:
            logger.error("Неизвестный тип обновления в process_payment")
            return
        
        logger.info(f"Обработка оплаты для пользователя {user.id}, товар {order_data['product_id']}")
        
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        
        # Проверяем наличие вариации еще раз
        cursor.execute("SELECT stock FROM product_variations WHERE id = ?", (order_data['variation_id'],))
        result = cursor.fetchone()
        
        if not result:
            await send_message_func("❌ Вариация товара не найдена в базе данных.")
            conn.close()
            return
            
        current_stock = result[0]
        
        if current_stock <= 0:
            error_msg = f"❌ Извините, вариация '{order_data['variation_name']}' временно отсутствует в наличии."
            await send_message_func(error_msg)
            conn.close()
            return
        
        # Создаем заказ
        cursor.execute('''
            INSERT INTO orders (user_id, user_name, product_variation_id, product_name, variation_name, quantity, total_price, payment_method, comment, status, pickup_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user.id, 
            user.first_name, 
            order_data['variation_id'], 
            order_data['product_name'], 
            order_data['variation_name'],
            1, 
            order_data['price'], 
            order_data['payment_method'], 
            comment, 
            'new', 
            'not_arrived'
        ))
        
        # Уменьшаем остаток товара
        cursor.execute("UPDATE product_variations SET stock = stock - 1 WHERE id = ?", (order_data['variation_id'],))
        
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Заказ #{order_id} создан для пользователя {user.id}")
        
        # Сообщение пользователю
        shop_address = get_shop_address()
        order_message = f"""✅ Заказ оформлен!

📦 Товар: {order_data['product_name']}
🎨 Вариация: {order_data['variation_name']}
💵 Цена: {order_data['price']} руб.
💳 Способ оплаты: {order_data['payment_method']}"""
        
        if comment:
            order_message += f"\n💬 Комментарий: {comment}"
            
        order_message += f"""\n🆔 Номер заказа: {order_id}

🏪 Адрес получения:\n{shop_address}

Выберите когда заберете товар:"""
        
        await send_message_func(order_message, reply_markup=get_pickup_keyboard(order_id))
        
        # Сообщение администратору
        admin_message = f"""🛒 НОВЫЙ ЗАКАЗ!

👤 Покупатель: {user.first_name} (@{user.username or 'нет'})
🆔 ID: {user.id}
📦 Товар: {order_data['product_name']}
🎨 Вариация: {order_data['variation_name']}
💵 Цена: {order_data['price']} руб.
💳 Способ оплаты: {order_data['payment_method']}"""
        
        if comment:
            admin_message += f"\n💬 Комментарий: {comment}"
            
        admin_message += f"""\n🆔 Номер заказа: {order_id}
📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ Требуется ваше внимание!"""
        
        try:
            await context.bot.send_message(chat_id=OWNER_ID, text=admin_message)
            logger.info(f"Уведомление о новом заказе #{order_id} отправлено администратору")
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение администратору: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка в process_payment: {e}", exc_info=True)
        error_msg = "❌ Произошла ошибка при оформлении заказа. Пожалуйста, попробуйте еще раз."
        await send_message_func(error_msg, reply_markup=get_main_keyboard())

async def send_pickup_reminder(context: ContextTypes.DEFAULT_TYPE):
    order_id = context.job.data
    
    # Используем context.application.bot_data для доступа к глобальным данным администратора
    if 'pending_pickups' not in context.application.bot_data:
        logger.warning(f"Напоминание для заказа #{order_id} отменено: отсутствуют данные чата администратора.")
        return

    pending_pickups = context.application.bot_data['pending_pickups']

    if order_id in pending_pickups:
        pickup_info = pending_pickups[order_id]
        last_reminder_time = pickup_info['last_reminder_time']
        
        # Отправлять напоминание, если прошло 30 секунд с последнего
        if datetime.now() - last_reminder_time > timedelta(seconds=30):
            conn = sqlite3.connect('shop.db')
            cursor = conn.cursor()
            cursor.execute("SELECT product_name, total_price, user_name FROM orders WHERE id = ?", (order_id,))
            order = cursor.fetchone()
            conn.close()

            if order:
                product_name, total_price, customer_user_name = order
                admin_alert_message = f"""🚨 НАПОМИНАНИЕ: ПОКУПАТЕЛЬ ЖДЕТ! 🚨

👤 Покупатель: {customer_user_name}
📦 Заказ: {product_name}
💵 Сумма: {total_price} руб.
🆔 Номер заказа: {order_id}

Нажмите 'Выхожу с товаром', чтобы подтвердить выдачу."""

                try:
                    await context.bot.edit_message_text(
                        chat_id=OWNER_ID,
                        message_id=pickup_info['admin_message_id'],
                        text=admin_alert_message,
                        reply_markup=get_admin_order_actions_keyboard(order_id)
                    )
                    pickup_info['last_reminder_time'] = datetime.now() # Обновляем время последнего напоминания
                    logger.info(f"Отправлено напоминание администратору о заказе #{order_id}")
                except Exception as e:
                    logger.error(f"Не удалось обновить сообщение администратора для заказа #{order_id}: {e}")
            
        # Планируем следующее напоминание
        context.job_queue.run_once(send_pickup_reminder, 30, data=order_id, name=f"pickup_reminder_{order_id}")
    else:
        logger.info(f"Напоминание для заказа #{order_id} отменено: заказ уже обработан или отменен.")

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    
    # Панель администратора
    if user_id == OWNER_ID:
        if text == "🏠 Главное меню":
            await start(update, context)
        elif text == "📦 Управление товарами":
            await manage_products(update, context)
        elif text == "➕ Добавить товар":
            await add_product(update, context)
        elif text == "📋 Список товаров":
            await list_products(update, context)
        elif text == "⬅️ Назад":
            await update.message.reply_text("👑 Панель администратора", reply_markup=get_owner_keyboard())
        elif text == "🏪 Установить адрес":
            context.user_data['awaiting_address'] = True
            await update.message.reply_text(
                f"🏪 Текущий адрес: {get_shop_address()}\n\nВведите новый адрес магазина:"
            )
        elif text == "📊 Статистика":
            conn = sqlite3.connect('shop.db')
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM products")
            total_products = cursor.fetchone()[0]
            cursor.execute("SELECT SUM(stock) FROM product_variations")
            total_stock = cursor.fetchone()[0] or 0
            cursor.execute("SELECT COUNT(*) FROM orders")
            total_orders = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'new'")
            new_orders = cursor.fetchone()[0]
            conn.close()
            
            stats_text = f"""📊 Статистика магазина:

📦 Товаров в каталоге: {total_products}
📦 Общий остаток: {total_stock} шт.
📋 Всего заказов: {total_orders}
🆕 Новых заказов: {new_orders}
🏪 Адрес: {get_shop_address()}"""
            await update.message.reply_text(stats_text)
        elif text == "📋 Заказы":
            conn = sqlite3.connect('shop.db')
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 10")
            orders = cursor.fetchall()
            conn.close()
            
            if not orders:
                await update.message.reply_text("📋 Заказов пока нет.")
            else:
                orders_text = "📋 Последние заказы:\n\n"
                for order in orders:
                    order_id, user_id, user_name, product_variation_id, product_name, variation_name, quantity, total_price, payment_method, comment, status, pickup_status, created_at = order
                    status_icon = "🚨" if pickup_status == 'arrived' else "⏳"
                    orders_text += f"{status_icon} {order_id}: {product_name} - {total_price} руб. ({variation_name})\n"
                    if comment:
                        orders_text += f"   💬 {comment}\n"
                orders_text += f"\n🏪 Адрес магазина:\n{get_shop_address()}"
                await update.message.reply_text(orders_text)
        elif text == "🧹 Очистить данные бота":
            await update.message.reply_text(
                "⚠️ Вы уверены, что хотите очистить ВСЕ данные бота (заказы и товары)? Это действие необратимо!",
                reply_markup=get_confirm_clear_keyboard()
            )
        elif text == "📦 Управление вариациями":
            await send_manage_products_for_variations(update, context)
            
        elif text == "⏭️ Пропустить комментарий":
            if context.user_data.get('awaiting_comment') and 'current_order' in context.user_data:
                order_data = context.user_data['current_order'].copy()
                context.user_data.pop('awaiting_comment', None)
                context.user_data.pop('current_order', None)
                await process_payment(update, context, order_data, None)
        elif text == "❌ Отмена заказа":
            context.user_data.pop('awaiting_comment', None)
            context.user_data.pop('current_order', None)
            await update.message.reply_text("❌ Заказ отменен.", reply_markup=get_main_keyboard())
        elif context.user_data.get('awaiting_comment') and 'current_order' in context.user_data:
            comment = text.strip()
            order_data = context.user_data['current_order'].copy()
            context.user_data.pop('awaiting_comment', None)
            context.user_data.pop('current_order', None)
            await process_payment(update, context, order_data, comment)
        elif context.user_data.get('awaiting_address'):
            set_shop_address(text)
            context.user_data['awaiting_address'] = False
            await update.message.reply_text(
                f"✅ Адрес успешно установлен!\n\n🏪 Новый адрес:\n{text}",
                reply_markup=get_owner_keyboard()
            )
        elif context.user_data.get('awaiting_product_name'):
            if 'product_category' not in context.user_data:
                await update.message.reply_text("❌ Сначала выберите категорию для товара.", reply_markup=get_category_selection_keyboard())
                return

            context.user_data['product_name'] = text
            context.user_data['awaiting_product_name'] = False
            context.user_data['awaiting_product_price'] = True
            await update.message.reply_text("💵 Введите цену товара:")
        elif context.user_data.get('awaiting_product_price'):
            try:
                price = float(text)
                context.user_data['product_price'] = price
                context.user_data['awaiting_product_price'] = False
                context.user_data['awaiting_product_photo'] = True
                await update.message.reply_text("📸 Отправьте фотографию товара или нажмите \'Пропустить комментарий\' чтобы пропустить.")

            except ValueError:
                await update.message.reply_text("❌ Цена должна быть числом! Введите цену:")

        elif context.user_data.get('awaiting_product_photo'):
            photo_id = None
            if update.message.photo:
                photo_id = update.message.photo[-1].file_id
            elif update.message.text and update.message.text.lower() == "пропустить комментарий":
                photo_id = None
            else:
                await update.message.reply_text("❌ Пожалуйста, отправьте фотографию или нажмите 'Пропустить комментарий'.")
                return

            name = context.user_data['product_name']
            price = context.user_data['product_price']
            category = context.user_data['product_category']
            
            conn = sqlite3.connect('shop.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO products (name, description, price, category, photo)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, 'Описание отсутствует', price, category, photo_id))
            conn.commit()
            conn.close()

            await update.message.reply_text(
                f"✅ Товар успешно добавлен!\n\n📦 {name}\n📂 Категория: {category}\n💵 {price} руб.\n📦 Количество: 0 шт.",
                reply_markup=get_products_keyboard()
            )
            
            context.user_data.clear()
  
        elif context.user_data.get('awaiting_stock_input'):
            product_id = context.user_data['awaiting_stock_input']
            try:
                new_stock = int(text)
                if new_stock < 0:
                    await update.message.reply_text("❌ Количество не может быть отрицательным! Введите количество: ")
                    return
                
                conn = sqlite3.connect('shop.db')
                cursor = conn.cursor()
                cursor.execute("UPDATE products SET stock = ? WHERE id = ?", (new_stock, product_id))
                conn.commit()
                conn.close()

                await update.message.reply_text(f"✅ Количество товара для ID {product_id} установлено на {new_stock} шт.", reply_markup=get_products_keyboard())
                context.user_data.pop('awaiting_stock_input')
            except ValueError:
                await update.message.reply_text("❌ Количество должно быть целым числом! Введите количество:")
    
        elif context.user_data.get('awaiting_new_variation_attribute_name'):
            product_id = context.user_data['awaiting_new_variation_attribute_name']
            attribute_name = text.strip()
            context.user_data['new_variation_attribute_name'] = attribute_name
            context.user_data['awaiting_new_variation_attribute_name'] = False
            context.user_data['awaiting_new_variation_attribute_value'] = product_id
            await update.message.reply_text(f"➕ Для товара ID {product_id}, атрибут '{attribute_name}': Введите значение атрибута (например, 'Красный', 'Яблоко'):")
        
        elif context.user_data.get('awaiting_new_variation_attribute_value'):
            product_id = context.user_data['awaiting_new_variation_attribute_value']
            attribute_value = text.strip()
            attribute_name = context.user_data['new_variation_attribute_name']
            context.user_data['new_variation_attribute_value'] = attribute_value
            context.user_data['awaiting_new_variation_attribute_value'] = False
            context.user_data['awaiting_new_variation_stock'] = product_id
            await update.message.reply_text(f"➕ Для товара ID {product_id}, атрибут '{attribute_name}: {attribute_value}': Введите начальное количество вариации (целое число):")
        
        elif context.user_data.get('awaiting_new_variation_stock'):
            product_id = context.user_data['awaiting_new_variation_stock']
            try:
                stock = int(text)
                if stock < 0:
                    await update.message.reply_text("❌ Количество не может быть отрицательным! Введите количество: ")
                    return
                attribute_name = context.user_data.get('new_variation_attribute_name')
                attribute_value = context.user_data.get('new_variation_attribute_value')
                
                if not attribute_name or not attribute_value:
                    logger.error(f"Ошибка: Отсутствуют данные атрибутов вариации в context.user_data для product_id {product_id}")
                    await update.message.reply_text("❌ Произошла ошибка при добавлении вариации. Пожалуйста, попробуйте снова.")
                    context.user_data.clear()
                    return

                conn = sqlite3.connect('shop.db')
                cursor = conn.cursor()
                cursor.execute("INSERT INTO product_variations (product_id, attribute_name, attribute_value, stock) VALUES (?, ?, ?, ?)",
                               (product_id, attribute_name, attribute_value, stock))
                conn.commit()
                conn.close()
                
                await update.message.reply_text(f"✅ Новая вариация '{attribute_name}: {attribute_value}' для товара ID {product_id} успешно добавлена с количеством {stock} шт.", reply_markup=get_products_keyboard())
                context.user_data.pop('awaiting_new_variation_attribute_name', None)
                context.user_data.pop('new_variation_attribute_name', None)
                context.user_data.pop('awaiting_new_variation_attribute_value', None)
                context.user_data.pop('new_variation_attribute_value', None)
                context.user_data.pop('awaiting_new_variation_stock', None)
                # Вернуться к управлению вариациями для этого продукта
                await send_manage_variations_keyboard(update, context, update.message.message_id, product_id)

            except ValueError:
                await update.message.reply_text("❌ Количество должно быть целым числом! Введите количество:")
        
        elif context.user_data.get('awaiting_variation_value_and_stock_input'):
            variation_id = context.user_data['awaiting_variation_value_and_stock_input']
            try:
                parts = text.split()
                if len(parts) != 2:
                    await update.message.reply_text("❌ Пожалуйста, введите новое значение атрибута и количество, разделенные пробелом (например, 'Красный 10').")
                    return
                
                new_attribute_value = parts[0].strip()
                new_stock = int(parts[1].strip())

                if new_stock < 0:
                    await update.message.reply_text("❌ Количество не может быть отрицательным! Введите количество:")
                    return

                conn = sqlite3.connect('shop.db')
                cursor = conn.cursor()
                cursor.execute("UPDATE product_variations SET attribute_value = ?, stock = ? WHERE id = ?", (new_attribute_value, new_stock, variation_id))
                conn.commit()
                conn.close()

                await update.message.reply_text(f"✅ Вариация ID {variation_id} успешно обновлена.", reply_markup=get_products_keyboard())
                context.user_data.pop('awaiting_variation_value_and_stock_input', None)
                context.user_data.pop('current_variation_attribute_name', None)
                
                message_id_to_edit = context.user_data.pop('variation_edit_message_id', None)
                product_id_to_return = context.user_data.pop('product_id_for_variation_management', None)

                if message_id_to_edit and product_id_to_return:
                    await send_manage_variations_keyboard(update, context, message_id_to_edit, product_id_to_return)
                else:
                    # Fallback, если что-то пошло не так, и мы не смогли отредактировать сообщение
                    await update.message.reply_text("✅ Вариация успешно обновлена.", reply_markup=get_products_keyboard())
                    await list_products(update, context)

            except ValueError:
                await update.message.reply_text("❌ Количество должно быть целым числом! Введите количество:")

    # Пользовательское меню
    else:
        if text == "🛍️ Каталог товаров":
            await show_catalog(update, context)
        elif text == "🛒 Мои заказы":
            conn = sqlite3.connect('shop.db')
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
            orders = cursor.fetchall()
            conn.close()
            
            if not orders:
                await update.message.reply_text("📦 У вас пока нет заказов.")
            else:
                orders_text = "🛒 Ваши заказы:\n\n"
                for order in orders:
                    order_id, user_id, user_name, product_variation_id, product_name, variation_name, quantity, total_price, payment_method, comment, status, pickup_status, created_at = order
                    status_text = "🚨 На месте" if pickup_status == 'arrived' else "⏳ Ожидает"
                    orders_text += f"🆔 {order_id}: {product_name} - {total_price} руб. ({status_text})\n"
                orders_text += f"\n🏪 Адрес магазина:\n{get_shop_address()}"
                await update.message.reply_text(orders_text)
        elif text == "📞 Контакты":
            await update.message.reply_text(
                f"📞 Контакты\n\n🏪 Адрес:\n{get_shop_address()}\n\nСвяжитесь с нами: @vape_kud"
            )
        elif text == "ℹ️ О нас":
            await update.message.reply_text(
                f"ℹ️ О нас\n\nДобро пожаловать в наш магазин!\n\n🏪 Наш адрес:\n{get_shop_address()}"
            )
        elif text == "⏭️ Пропустить комментарий":
            if context.user_data.get('awaiting_comment') and 'current_order' in context.user_data:
                order_data = context.user_data['current_order'].copy()
                context.user_data.pop('awaiting_comment', None)
                context.user_data.pop('current_order', None)
                await process_payment(update, context, order_data, None)
        elif text == "❌ Отмена заказа":
            context.user_data.pop('awaiting_comment', None)
            context.user_data.pop('current_order', None)
            await update.message.reply_text("❌ Заказ отменен.", reply_markup=get_main_keyboard())
        elif context.user_data.get('awaiting_comment') and 'current_order' in context.user_data:
            comment = text.strip()
            order_data = context.user_data['current_order'].copy()
            context.user_data.pop('awaiting_comment', None)
            context.user_data.pop('current_order', None)
            await process_payment(update, context, order_data, comment)
        else:
            await update.message.reply_text("Используйте кнопки для навигации", reply_markup=get_main_keyboard())

def main():
    """Основная функция запуска бота"""
    # Инициализация базы данных
    init_db()
    
    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).arbitrary_callback_data(True).build()
    
    # Инициализация глобальных данных для администратора
    application.bot_data['pending_pickups'] = {}

    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_message))
    
    # Запуск бота
    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()