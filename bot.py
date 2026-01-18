"""
School Portal Telegram Bot
- Teacher notifications for new submissions
- Teacher verification and linking
- Teacher can view students and pending submissions
- Students use web interface only (no Telegram)
"""

import os
import logging
import re
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
from pymongo import MongoClient

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MONGODB_URI = os.getenv('MONGODB_URI')

# Initialize MongoDB
client = None
db = None

def init_db():
    global client, db
    mongo_uri = MONGODB_URI or os.getenv('MONGO_URL')
    if mongo_uri:
        client = MongoClient(mongo_uri)
        db_name = os.getenv('MONGODB_DB', 'school_portal')
        db = client.get_database(db_name)
        logger.info("Connected to MongoDB")
    else:
        logger.error("MONGODB_URI or MONGO_URL not set")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message"""
    chat_id = update.effective_chat.id
    
    # Check if teacher
    teacher = None
    if db:
        teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    if teacher:
        message = f"""👋 Welcome back, {teacher.get('name', 'Teacher')}!

📚 *Your Commands:*
/students - View your students
/submissions - View pending submissions
/help - Show help

You will receive notifications for new student submissions."""
    else:
        message = f"""👋 Welcome to the School Portal Bot!

Your Telegram ID: `{chat_id}`

*For Teachers:*
Use `/verify <teacher_id>` to link your account.

Example: `/verify T001`

Once linked, you'll receive notifications when students submit assignments."""
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def verify_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Link Telegram ID to teacher account"""
    if db is None:
        await update.message.reply_text("❌ Database not connected.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "⚠️ Please provide your teacher ID.\n\n"
            "Usage: `/verify T001`",
            parse_mode='Markdown'
        )
        return
    
    teacher_id_input = context.args[0]
    chat_id = update.effective_chat.id
    
    # Case-insensitive search
    teacher = db.teachers.find_one({
        'teacher_id': {'$regex': f'^{re.escape(teacher_id_input)}$', '$options': 'i'}
    })
    
    if not teacher:
        available = list(db.teachers.find({}, {'teacher_id': 1, 'name': 1}).limit(5))
        teacher_list = ", ".join([f"{t.get('teacher_id')}" for t in available])
        
        await update.message.reply_text(
            f"❌ Teacher ID `{teacher_id_input}` not found.\n\n"
            f"Available: {teacher_list if teacher_list else 'None'}",
            parse_mode='Markdown'
        )
        return
    
    teacher_id = teacher['teacher_id']
    
    # Check if already linked to another
    existing = db.teachers.find_one({'telegram_id': chat_id})
    if existing and existing['teacher_id'] != teacher_id:
        await update.message.reply_text(f"⚠️ Already linked to `{existing['teacher_id']}`.", parse_mode='Markdown')
        return
    
    # Link account
    db.teachers.update_one(
        {'teacher_id': teacher_id},
        {'$set': {'telegram_id': chat_id, 'telegram_verified_at': datetime.utcnow()}}
    )
    
    await update.message.reply_text(
        f"✅ *Verification Complete!*\n\n"
        f"Welcome, {teacher.get('name', 'Teacher')}!\n"
        f"Linked to: `{teacher_id}`\n\n"
        "You will now receive:\n"
        "📬 New submission notifications\n"
        "📱 Student messages\n\n"
        "Use /submissions to see pending reviews.",
        parse_mode='Markdown'
    )

async def list_students(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show teacher's students"""
    if db is None:
        await update.message.reply_text("❌ Database not connected.")
        return
    
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    if not teacher:
        await update.message.reply_text("⚠️ Not linked. Use `/verify <teacher_id>`", parse_mode='Markdown')
        return
    
    students = list(db.students.find({'teachers': teacher['teacher_id']}))
    
    if not students:
        await update.message.reply_text("📚 No students assigned yet.")
        return
    
    # Group by class
    by_class = {}
    for s in students:
        cls = s.get('class', 'Unknown')
        if cls not in by_class:
            by_class[cls] = []
        by_class[cls].append(s)
    
    message = f"👨‍🏫 *Your Students* ({len(students)} total)\n\n"
    
    for cls in sorted(by_class.keys()):
        message += f"📖 *Class {cls}*\n"
        for s in sorted(by_class[cls], key=lambda x: x.get('name', '')):
            message += f"  • {s.get('name', 'Unknown')} (`{s.get('student_id')}`)\n"
        message += "\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def list_submissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show pending submissions"""
    if db is None:
        await update.message.reply_text("❌ Database not connected.")
        return
    
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    if not teacher:
        await update.message.reply_text("⚠️ Not linked. Use `/verify <teacher_id>`", parse_mode='Markdown')
        return
    
    # Get teacher's assignments
    assignments = list(db.assignments.find({'teacher_id': teacher['teacher_id']}))
    assignment_ids = [a['assignment_id'] for a in assignments]
    assignment_map = {a['assignment_id']: a for a in assignments}
    
    # Get pending submissions
    pending = list(db.submissions.find({
        'assignment_id': {'$in': assignment_ids},
        'status': {'$in': ['submitted', 'ai_reviewed']}
    }).sort('submitted_at', -1).limit(20))
    
    if not pending:
        await update.message.reply_text("✅ No pending submissions! All caught up.")
        return
    
    web_url = os.getenv('WEB_URL', 'http://localhost:5000')
    message = f"📝 *Pending Submissions* ({len(pending)})\n\n"
    
    for sub in pending:
        assignment = assignment_map.get(sub['assignment_id'], {})
        student = db.students.find_one({'student_id': sub['student_id']})
        student_name = student.get('name', 'Unknown') if student else 'Unknown'
        
        submitted_at = sub.get('submitted_at', datetime.utcnow())
        time_str = submitted_at.strftime('%d %b, %H:%M') if isinstance(submitted_at, datetime) else str(submitted_at)
        
        status_emoji = '🤖' if sub['status'] == 'ai_reviewed' else '⏳'
        
        message += f"{status_emoji} *{assignment.get('title', 'Assignment')}*\n"
        message += f"   👤 {student_name}\n"
        message += f"   🕐 {time_str}\n"
        message += f"   🔗 [Review]({web_url}/teacher/review/{sub['submission_id']})\n\n"
    
    await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)

async def handle_teacher_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process replies to student messages"""
    if db is None:
        return
    
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    if not teacher:
        return
    
    if not update.message.reply_to_message:
        return
    
    original_text = update.message.reply_to_message.text
    if not original_text or '📱' not in original_text:
        return
    
    # Extract student name from format: "📱 StudentName: message"
    match = re.match(r'📱\s*([^:]+):', original_text)
    if not match:
        return
    
    student_name = match.group(1).strip()
    reply_text = update.message.text
    
    student = db.students.find_one({'name': {'$regex': student_name, '$options': 'i'}})
    
    if not student:
        await update.message.reply_text(f"⚠️ Student '{student_name}' not found.")
        return
    
    # Save reply to messages
    db.messages.insert_one({
        'student_id': student['student_id'],
        'teacher_id': teacher['teacher_id'],
        'message': reply_text,
        'from_student': False,
        'timestamp': datetime.utcnow(),
        'read': False,
        'sent_via': 'telegram'
    })
    
    await update.message.reply_text(f"✅ Reply sent to {student_name}!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help"""
    help_text = """📚 *School Portal Bot - Teacher Help*

*Commands:*
/start - Welcome message
/verify <id> - Link your teacher account
/students - View your students list
/submissions - View pending submissions
/help - Show this help

*Notifications:*
📬 New assignment submissions
📱 Student messages

*Reply to Messages:*
When a student sends you a message through the web portal, you'll receive it here. Simply reply to that message to respond!

*Web Portal:*
Use the web portal for full review functionality, including side-by-side feedback editing."""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown commands"""
    await update.message.reply_text(
        "❓ Unknown command.\nUse /help to see available commands."
    )

def main():
    """Initialize and run the bot"""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("verify", verify_teacher))
    application.add_handler(CommandHandler("students", list_students))
    application.add_handler(CommandHandler("submissions", list_submissions))
    application.add_handler(CommandHandler("help", help_command))
    
    # Handle teacher replies to student messages
    application.add_handler(MessageHandler(
        filters.REPLY & filters.TEXT & ~filters.COMMAND,
        handle_teacher_reply
    ))
    
    # Unknown commands
    application.add_handler(MessageHandler(filters.COMMAND, handle_unknown))
    
    logger.info("Starting bot (teacher notifications only)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
