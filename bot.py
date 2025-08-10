"""Telegram bot interface for Grobovsheke SmsBomber.

The bot asks for a phone number and a repeat count and then
launches the existing asynchronous attack from Core.Run.

Provide the bot token either via the ``BOT_TOKEN`` environment variable
or with the ``--token`` command-line option.
"""

import argparse
import asyncio
import os

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from Core.Run import start_async_attacks


# Conversation states
NUMBER, REPEAT = range(2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for /start command."""
    user_id = update.effective_user.id if update.effective_user else 'unknown user'
    print(f"/start from {user_id}")
    await update.message.reply_text("Введите номер телефона без '+'")
    return NUMBER


async def get_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive phone number from user."""
    number = update.message.text.strip()
    if not number.isdigit():
        await update.message.reply_text('Пожалуйста, отправьте только цифры номера.')
        return NUMBER
    context.user_data['number'] = number
    user_id = update.effective_user.id if update.effective_user else 'unknown user'
    print(f"Received number {number} from {user_id}")
    await update.message.reply_text('Сколько повторов? (1-1000)')
    return REPEAT


async def get_repeats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive repeat count and start attack."""
    repeats_text = update.message.text.strip()
    if not repeats_text.isdigit():
        await update.message.reply_text('Введите количество повторов числом.')
        return REPEAT
    repeats = int(repeats_text)
    if repeats <= 0 or repeats > 1000:
        await update.message.reply_text('Введите число от 1 до 1000.')
        return REPEAT

    number = context.user_data['number']
    print(f"Starting attack for {number} with {repeats} repeats")
    await update.message.reply_text('Атака запущена.')

    # Run the attack in a separate thread to avoid blocking the bot.
    await asyncio.to_thread(start_async_attacks, number, repeats)

    print(f"Attack finished for {number}")
    await update.message.reply_text('Атака завершена.')
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    user_id = update.effective_user.id if update.effective_user else 'unknown user'
    print(f"Conversation cancelled by {user_id}")
    await update.message.reply_text('Отменено.')
    return ConversationHandler.END


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
        entry_points=[CommandHandler('start', start)],
        states={
            NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_number)],
            REPEAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_repeats)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)

    application.run_polling()


if __name__ == '__main__':
    main()

