"""Telegram bot interface for Grobovsheke SmsBomber.

The bot asks for a phone number and a repeat count and then
launches the existing asynchronous attack from Core.Run.


Provide the bot token either via the ``BOT_TOKEN`` environment variable
or with the ``--token`` command-line option.
"""

import argparse
import asyncio
import os
import threading

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,

    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from Core.Run import start_async_attacks


# Conversation states
NUMBER, REPEAT = range(2)


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show main menu with reply buttons."""
    user_id = update.effective_user.id if update.effective_user else 'unknown user'
    print(f"/start from {user_id}")
    keyboard = [["🚀 Start attack"], ["📜 History of Attacks"], ["💰 Balance"]]
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )


async def start_attack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Begin attack conversation after user presses Start attack."""
    user_id = update.effective_user.id if update.effective_user else 'unknown user'
    print(f"Start attack pressed by {user_id}")
    await update.message.reply_text("📱 Введите номер телефона без '+'")
    return NUMBER


async def get_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive phone number from user."""
    number = update.message.text.strip()
    if not number.isdigit():

        await update.message.reply_text('❗ Пожалуйста, отправьте только цифры номера.')
        return NUMBER
    context.user_data['number'] = number
    user_id = update.effective_user.id if update.effective_user else 'unknown user'
    print(f"Received number {number} from {user_id}")
    await update.message.reply_text('🔁 Сколько повторов? (1-1000)')

    return REPEAT


async def get_repeats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive repeat count and start attack."""
    repeats_text = update.message.text.strip()
    if not repeats_text.isdigit():
        await update.message.reply_text('❗ Введите количество повторов числом.')
        return REPEAT
    repeats = int(repeats_text)
    if repeats <= 0 or repeats > 1000:
        await update.message.reply_text('❗ Введите число от 1 до 1000.')
        return REPEAT

    number = context.user_data['number']
    print(f"Starting attack for {number} with {repeats} repeats")

    attack_id = context.application.bot_data.get('attack_counter', 0) + 1
    context.application.bot_data['attack_counter'] = attack_id

    stop_event = threading.Event()
    attacks = context.application.bot_data.setdefault('attacks', {})

    message = await update.message.reply_text(
        f"🚀 Атака #{attack_id} запущена\n"
        f"📱 Номер: {number}\n"
        f"🔁 Повторы: {repeats}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton('🛑 Остановить', callback_data=f'stop_{attack_id}')]]
        ),
    )

    loop = asyncio.get_running_loop()

    async def send_progress(count: int) -> None:
        await context.bot.send_message(
            chat_id=message.chat_id, text=f"🔁 Повторы: {count}/{repeats}"
        )

    async def send_info(info: dict) -> None:
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=(
                "🌐 Запрос: "
                f"{info.get('website', 'N/A')} | {info.get('attack', 'N/A')} | "
                f"{info.get('country', 'N/A')} | anonymous: {info.get('anonymous', 'N/A')}"
            ),
        )

    def progress_callback(count: int) -> None:
        loop.call_soon_threadsafe(lambda: context.application.create_task(send_progress(count)))

    def info_callback(info: dict) -> None:
        loop.call_soon_threadsafe(lambda: context.application.create_task(send_info(info)))

    async def run_attack() -> None:
        completed = await asyncio.to_thread(
            start_async_attacks,
            number,
            repeats,
            stop_event,
            progress_callback,
            info_callback,
        )

        try:
            await context.bot.edit_message_reply_markup(
                chat_id=message.chat_id, message_id=message.message_id, reply_markup=None
            )
        except Exception:
            pass
        status = 'completed' if completed == repeats and not stop_event.is_set() else 'cancelled'
        emoji = '✅' if status == 'completed' else '⛔'
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=f"{emoji} Атака #{attack_id} {'завершена' if status=='completed' else 'остановлена'}."
                 f" Циклы: {completed}/{repeats}",
        )
        history = context.user_data.setdefault('history', [])
        history.append({'id': attack_id, 'number': number, 'repeats': repeats, 'completed': completed, 'status': status})
        attacks.pop(attack_id, None)

    task = context.application.create_task(run_attack())
    attacks[attack_id] = {'stop': stop_event, 'task': task}


    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    user_id = update.effective_user.id if update.effective_user else 'unknown user'
    print(f"Conversation cancelled by {user_id}")
    await update.message.reply_text('❌ Отменено.')
    return ConversationHandler.END


async def stop_attack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle stop button press."""
    query = update.callback_query
    await query.answer()
    attack_id = int(query.data.split('_')[1])
    attacks = context.application.bot_data.get('attacks', {})
    attack = attacks.get(attack_id)
    if attack:
        attack['stop'].set()
        await query.edit_message_text(f"⏹ Остановка атаки #{attack_id}...")
    else:
        await query.edit_message_text(f"⚠️ Атака #{attack_id} уже завершена")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's attack history."""
    history = context.user_data.get('history', [])
    if not history:
        await update.message.reply_text('📜 История пуста.')
        return
    lines = []
    for item in history[-10:]:
        emoji = '✅' if item['status'] == 'completed' else '⛔'
        lines.append(f"{emoji} #{item['id']} {item['number']} {item['completed']}/{item['repeats']}")
    await update.message.reply_text('📜 История атак:\n' + '\n'.join(lines))


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Placeholder for balance button."""
    await update.message.reply_text('💰 Функция баланса в разработке.')


def main() -> None:

    parser = argparse.ArgumentParser(description='Run the Grobovsheke Telegram bot')
    parser.add_argument('--token', help='Telegram bot token')
    args = parser.parse_args()

    print('Starting Telegram bot')

    token = args.token or os.getenv('BOT_TOKEN')
    if not token:
        raise RuntimeError('Provide bot token via --token or BOT_TOKEN env variable')

    application = ApplicationBuilder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^🚀 Start attack$'), start_attack)],

        states={
            NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_number)],
            REPEAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_repeats)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(CommandHandler('start', show_menu))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(stop_attack, pattern=r'^stop_\d+$'))
    application.add_handler(CommandHandler('history', history))
    application.add_handler(MessageHandler(filters.Regex('^📜 History of Attacks$'), history))
    application.add_handler(MessageHandler(filters.Regex('^💰 Balance$'), balance))


    application.run_polling()


if __name__ == '__main__':
    main()

