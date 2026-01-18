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

# Initialize MongoDB connection
client = None
db = None

def init_db():
    global client, db
    # Support Railway's MONGO_URL or standard MONGODB_URI
    mongo_uri = MONGODB_URI or os.getenv('MONGO_URL')
    if mongo_uri:
        client = MongoClient(mongo_uri)
        db_name = os.getenv('MONGODB_DB', 'school_portal')
        db = client.get_database(db_name)
        logger.info("Connected to MongoDB")
    else:
        logger.error("MONGODB_URI or MONGO_URL not set")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message and show Telegram ID"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    welcome_message = f"""👋 Welcome to the School Portal Bot!

Your Telegram ID: `{chat_id}`

**For Teachers:**
Use `/verify <teacher_id>` to link your account.

**Commands:**
/verify <teacher_id> - Link your teacher account
/students - View your students
/submissions - View pending submissions
/help - Show this help message

Once verified, students can message you directly through the web portal, and you'll receive notifications here."""
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def verify_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Link Telegram ID to teacher account"""
    if not db:
        await update.message.reply_text("❌ Database not connected. Please try again later.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "⚠️ Please provide your teacher ID.\n"
            "Usage: `/verify T12345`",
            parse_mode='Markdown'
        )
        return
    
    teacher_id = context.args[0].upper()
    chat_id = update.effective_chat.id
    
    # Check if teacher exists
    teacher = db.teachers.find_one({'teacher_id': teacher_id})
    
    if not teacher:
        await update.message.reply_text(
            f"❌ Teacher ID `{teacher_id}` not found.\n"
            "Please check your ID and try again.",
            parse_mode='Markdown'
        )
        return
    
    # Check if already linked to another account
    existing = db.teachers.find_one({'telegram_id': chat_id})
    if existing and existing['teacher_id'] != teacher_id:
        await update.message.reply_text(
            f"⚠️ Your Telegram is already linked to teacher `{existing['teacher_id']}`.\n"
            "Contact admin if you need to change this.",
            parse_mode='Markdown'
        )
        return
    
    # Link the account
    db.teachers.update_one(
        {'teacher_id': teacher_id},
        {'$set': {'telegram_id': chat_id, 'telegram_verified_at': datetime.utcnow()}}
    )
    
    await update.message.reply_text(
        f"✅ Success! Your Telegram is now linked to teacher account `{teacher_id}`.\n\n"
        f"Welcome, {teacher.get('name', 'Teacher')}! 🎉\n\n"
        "You will now receive:\n"
        "• Student messages\n"
        "• Assignment submission notifications\n"
        "• System alerts\n\n"
        "Reply to any student message to respond directly!",
        parse_mode='Markdown'
    )

async def list_students(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show teacher's students"""
    if not db:
        await update.message.reply_text("❌ Database not connected.")
        return
    
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    if not teacher:
        await update.message.reply_text(
            "⚠️ Your Telegram is not linked to a teacher account.\n"
            "Use `/verify <teacher_id>` first.",
            parse_mode='Markdown'
        )
        return
    
    # Get students who have this teacher assigned
    students = list(db.students.find({'teachers': teacher['teacher_id']}))
    
    if not students:
        await update.message.reply_text("📚 No students assigned to you yet.")
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
            message += f"  • {s.get('name', 'Unknown')} (`{s.get('student_id', 'N/A')}`)\n"
        message += "\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def list_submissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show pending submissions for review"""
    if not db:
        await update.message.reply_text("❌ Database not connected.")
        return
    
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    if not teacher:
        await update.message.reply_text(
            "⚠️ Your Telegram is not linked to a teacher account.\n"
            "Use `/verify <teacher_id>` first.",
            parse_mode='Markdown'
        )
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
        await update.message.reply_text("✅ No pending submissions to review!")
        return
    
    web_url = os.getenv('WEB_URL', 'http://localhost:5000')
    message = f"📝 *Pending Submissions* ({len(pending)})\n\n"
    
    for sub in pending:
        assignment = assignment_map.get(sub['assignment_id'], {})
        student = db.students.find_one({'student_id': sub['student_id']})
        student_name = student.get('name', 'Unknown') if student else 'Unknown'
        
        submitted_at = sub.get('submitted_at', datetime.utcnow())
        if isinstance(submitted_at, datetime):
            time_str = submitted_at.strftime('%d %b, %H:%M')
        else:
            time_str = str(submitted_at)
        
        status_emoji = '🤖' if sub['status'] == 'ai_reviewed' else '⏳'
        
        message += f"{status_emoji} *{assignment.get('title', 'Assignment')}*\n"
        message += f"   👤 {student_name}\n"
        message += f"   🕐 {time_str}\n"
        message += f"   🔗 [Review]({web_url}/teacher/submissions/{sub['submission_id']}/review)\n\n"
    
    await update.message.reply_text(
        message, 
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

async def handle_teacher_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process replies to student messages"""
    if not db:
        return
    
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    if not teacher:
        return  # Not a verified teacher
    
    # Check if this is a reply to a student message
    if not update.message.reply_to_message:
        return
    
    original_text = update.message.reply_to_message.text
    if not original_text or '📱' not in original_text:
        return  # Not a student message
    
    # Extract student name from the original message format: "📱 StudentName: message"
    match = re.match(r'📱\s*([^:]+):', original_text)
    if not match:
        return
    
    student_name = match.group(1).strip()
    reply_text = update.message.text
    
    # Find the student
    student = db.students.find_one({'name': student_name})
    if not student:
        # Try partial match
        student = db.students.find_one({'name': {'$regex': student_name, '$options': 'i'}})
    
    if not student:
        await update.message.reply_text(
            f"⚠️ Could not find student '{student_name}' in database."
        )
        return
    
    # Save the reply to messages collection
    db.messages.insert_one({
        'student_id': student['student_id'],
        'teacher_id': teacher['teacher_id'],
        'message': reply_text,
        'from_student': False,
        'timestamp': datetime.utcnow(),
        'read': False,
        'sent_via': 'telegram'
    })
    
    await update.message.reply_text(
        f"✅ Reply sent to {student_name}!\n"
        "They will see it in the web portal."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help information"""
    help_text = """📚 *School Portal Bot - Help*

*Commands:*
/start - Welcome message and your Telegram ID
/verify <teacher_id> - Link your teacher account
/students - View list of your students
/submissions - View pending submissions
/help - Show this help

*How to respond to students:*
When a student sends you a message, you'll receive it here.
Simply *reply* to that message to send your response back!

*Notifications you'll receive:*
• 📱 Student messages
• 📚 New assignment submissions
• ⏰ Reminders (coming soon)

*Need help?*
Contact your school administrator."""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown commands"""
    await update.message.reply_text(
        "❓ I don't understand that command.\n"
        "Use /help to see available commands."
    )

def main():
    """Initialize and run the bot"""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    # Initialize database
    init_db()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("verify", verify_teacher))
    application.add_handler(CommandHandler("students", list_students))
    application.add_handler(CommandHandler("submissions", list_submissions))
    application.add_handler(CommandHandler("help", help_command))
    
    # Handle replies to messages (for teacher responses)
    application.add_handler(MessageHandler(
        filters.REPLY & filters.TEXT & ~filters.COMMAND,
        handle_teacher_reply
    ))
    
    # Handle unknown commands
    application.add_handler(MessageHandler(filters.COMMAND, handle_unknown))
    
    # Run the bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
