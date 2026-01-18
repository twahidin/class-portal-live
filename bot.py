"""
School Portal Telegram Bot
- Teacher notifications for submissions and reviews
- Assignment summaries and reports
- Reply to student messages
- Download PDF reports
"""

import os
import logging
import re
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
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
    
    teacher = None
    if db:
        teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    if teacher:
        message = f"""👋 Welcome back, {teacher.get('name', 'Teacher')}!

📚 *Commands:*
/students - View your students
/submissions - Pending submissions
/assignments - View assignments with summaries
/summary - Get class summary for an assignment
/report - Download PDF report
/help - Show all commands

You will receive notifications for new submissions and can reply to students here."""
    else:
        message = f"""👋 Welcome to the School Portal Bot!

Your Telegram ID: `{chat_id}`

*For Teachers:*
Use `/verify <teacher_id>` to link your account.

Example: `/verify T001`"""
    
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
    
    teacher = db.teachers.find_one({
        'teacher_id': {'$regex': f'^{re.escape(teacher_id_input)}$', '$options': 'i'}
    })
    
    if not teacher:
        available = list(db.teachers.find({}, {'teacher_id': 1}).limit(5))
        teacher_list = ", ".join([f"{t.get('teacher_id')}" for t in available])
        await update.message.reply_text(
            f"❌ Teacher ID `{teacher_id_input}` not found.\n\nAvailable: {teacher_list or 'None'}",
            parse_mode='Markdown'
        )
        return
    
    teacher_id = teacher['teacher_id']
    
    existing = db.teachers.find_one({'telegram_id': chat_id})
    if existing and existing['teacher_id'] != teacher_id:
        await update.message.reply_text(f"⚠️ Already linked to `{existing['teacher_id']}`.", parse_mode='Markdown')
        return
    
    db.teachers.update_one(
        {'teacher_id': teacher_id},
        {'$set': {'telegram_id': chat_id, 'telegram_verified_at': datetime.utcnow()}}
    )
    
    await update.message.reply_text(
        f"✅ *Verification Complete!*\n\n"
        f"Welcome, {teacher.get('name', 'Teacher')}!\n\n"
        "You will receive:\n"
        "📬 Submission notifications\n"
        "📱 Student messages\n\n"
        "Use /assignments to see your assignments.",
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
    
    by_class = {}
    for s in students:
        cls = s.get('class', 'Unknown')
        if cls not in by_class:
            by_class[cls] = []
        by_class[cls].append(s)
    
    message = f"👨‍🏫 *Your Students* ({len(students)} total)\n\n"
    
    for cls in sorted(by_class.keys()):
        message += f"📖 *Class {cls}* ({len(by_class[cls])} students)\n"
        for s in sorted(by_class[cls], key=lambda x: x.get('name', ''))[:10]:
            message += f"  • {s.get('name', 'Unknown')}\n"
        if len(by_class[cls]) > 10:
            message += f"  ... and {len(by_class[cls]) - 10} more\n"
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
    
    assignments = list(db.assignments.find({'teacher_id': teacher['teacher_id']}))
    assignment_ids = [a['assignment_id'] for a in assignments]
    assignment_map = {a['assignment_id']: a for a in assignments}
    
    pending = list(db.submissions.find({
        'assignment_id': {'$in': assignment_ids},
        'status': {'$in': ['submitted', 'ai_reviewed']}
    }).sort('submitted_at', -1).limit(15))
    
    if not pending:
        await update.message.reply_text("✅ No pending submissions!")
        return
    
    web_url = os.getenv('WEB_URL', 'http://localhost:5000')
    message = f"📝 *Pending Submissions* ({len(pending)})\n\n"
    
    for sub in pending:
        assignment = assignment_map.get(sub['assignment_id'], {})
        student = db.students.find_one({'student_id': sub['student_id']})
        student_name = student.get('name', 'Unknown') if student else 'Unknown'
        
        submitted_at = sub.get('submitted_at', datetime.utcnow())
        time_str = submitted_at.strftime('%d %b %H:%M') if isinstance(submitted_at, datetime) else 'N/A'
        
        status_emoji = '🤖' if sub['status'] == 'ai_reviewed' else '⏳'
        
        message += f"{status_emoji} *{assignment.get('title', 'Assignment')[:25]}*\n"
        message += f"   👤 {student_name} | 🕐 {time_str}\n\n"
    
    message += f"🔗 [Open Web Portal]({web_url}/teacher/submissions)"
    
    await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)

async def list_assignments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show teacher's assignments with submission stats"""
    if db is None:
        await update.message.reply_text("❌ Database not connected.")
        return
    
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    if not teacher:
        await update.message.reply_text("⚠️ Not linked. Use `/verify <teacher_id>`", parse_mode='Markdown')
        return
    
    assignments = list(db.assignments.find({
        'teacher_id': teacher['teacher_id'],
        'status': 'published'
    }).sort('created_at', -1).limit(10))
    
    if not assignments:
        await update.message.reply_text("📚 No assignments yet.")
        return
    
    # Create inline keyboard
    keyboard = []
    for a in assignments:
        # Get submission stats
        total_submissions = db.submissions.count_documents({
            'assignment_id': a['assignment_id'],
            'status': {'$in': ['submitted', 'ai_reviewed', 'reviewed']}
        })
        reviewed = db.submissions.count_documents({
            'assignment_id': a['assignment_id'],
            'status': 'reviewed'
        })
        
        label = f"📝 {a.get('title', 'Untitled')[:30]} ({reviewed}/{total_submissions})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"assign_{a['assignment_id']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📚 *Your Assignments*\n\n"
        "Select an assignment to view summary:\n"
        "(Reviewed/Total submissions shown)",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def assignment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle assignment selection"""
    query = update.callback_query
    await query.answer()
    
    if not query.data.startswith('assign_'):
        return
    
    assignment_id = query.data.replace('assign_', '')
    
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    assignment = db.assignments.find_one({
        'assignment_id': assignment_id,
        'teacher_id': teacher['teacher_id']
    })
    
    if not assignment:
        await query.edit_message_text("❌ Assignment not found.")
        return
    
    # Generate summary
    summary = await generate_assignment_summary(assignment, teacher)
    
    # Action buttons
    keyboard = [
        [InlineKeyboardButton("📊 Detailed Summary", callback_data=f"detail_{assignment_id}")],
        [InlineKeyboardButton("📥 Download PDF Report", callback_data=f"pdf_{assignment_id}")],
        [InlineKeyboardButton("🔙 Back to Assignments", callback_data="back_assignments")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        summary,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def generate_assignment_summary(assignment: dict, teacher: dict) -> str:
    """Generate a quick summary for an assignment"""
    assignment_id = assignment['assignment_id']
    
    # Get all submissions
    submissions = list(db.submissions.find({
        'assignment_id': assignment_id,
        'status': {'$in': ['submitted', 'ai_reviewed', 'reviewed']}
    }))
    
    total_students = db.students.count_documents({'teachers': teacher['teacher_id']})
    submitted_count = len(submissions)
    reviewed_count = len([s for s in submissions if s['status'] == 'reviewed'])
    pending_count = submitted_count - reviewed_count
    
    # Calculate score statistics
    scores = []
    for sub in submissions:
        if sub.get('final_marks') is not None:
            scores.append(sub['final_marks'])
    
    total_marks = assignment.get('total_marks', 100)
    
    summary = f"📝 *{assignment.get('title', 'Assignment')}*\n"
    summary += f"📖 {assignment.get('subject', 'N/A')} | Total: {total_marks} marks\n\n"
    
    summary += f"📊 *Submission Status*\n"
    summary += f"  • Submitted: {submitted_count}/{total_students}\n"
    summary += f"  • Reviewed: {reviewed_count}\n"
    summary += f"  • Pending Review: {pending_count}\n\n"
    
    if scores:
        avg_score = sum(scores) / len(scores)
        min_score = min(scores)
        max_score = max(scores)
        pass_count = len([s for s in scores if s >= total_marks * 0.5])
        
        summary += f"📈 *Score Summary* ({len(scores)} graded)\n"
        summary += f"  • Average: {avg_score:.1f}/{total_marks} ({avg_score/total_marks*100:.0f}%)\n"
        summary += f"  • Range: {min_score} - {max_score}\n"
        summary += f"  • Pass Rate: {pass_count}/{len(scores)} ({pass_count/len(scores)*100:.0f}%)\n\n"
        
        # Identify areas from AI feedback
        strengths, improvements = analyze_class_feedback(submissions)
        
        if strengths:
            summary += f"✅ *Areas of Strength*\n"
            for s in strengths[:3]:
                summary += f"  • {s}\n"
            summary += "\n"
        
        if improvements:
            summary += f"⚠️ *Areas to Address*\n"
            for i in improvements[:3]:
                summary += f"  • {i}\n"
    else:
        summary += "📈 _No scores available yet_\n"
    
    return summary

def analyze_class_feedback(submissions: list) -> tuple:
    """Analyze class feedback to identify patterns"""
    strengths = []
    improvements = []
    
    correct_counts = {}
    incorrect_counts = {}
    
    for sub in submissions:
        ai_feedback = sub.get('ai_feedback', {})
        questions = ai_feedback.get('questions', [])
        
        for q in questions:
            q_num = q.get('question_num', 0)
            if q.get('is_correct') == True:
                correct_counts[q_num] = correct_counts.get(q_num, 0) + 1
            elif q.get('is_correct') == False:
                incorrect_counts[q_num] = incorrect_counts.get(q_num, 0) + 1
    
    # Identify patterns
    total = len(submissions)
    if total > 0:
        for q_num, count in sorted(correct_counts.items(), key=lambda x: -x[1]):
            if count >= total * 0.7:
                strengths.append(f"Question {q_num}: {count}/{total} correct")
        
        for q_num, count in sorted(incorrect_counts.items(), key=lambda x: -x[1]):
            if count >= total * 0.5:
                improvements.append(f"Question {q_num}: {count}/{total} need improvement")
    
    return strengths, improvements

async def detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed assignment summary"""
    query = update.callback_query
    await query.answer()
    
    assignment_id = query.data.replace('detail_', '')
    
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    assignment = db.assignments.find_one({
        'assignment_id': assignment_id,
        'teacher_id': teacher['teacher_id']
    })
    
    if not assignment:
        await query.edit_message_text("❌ Assignment not found.")
        return
    
    # Get all submissions with details
    submissions = list(db.submissions.find({
        'assignment_id': assignment_id,
        'status': {'$in': ['submitted', 'ai_reviewed', 'reviewed']}
    }).sort('final_marks', -1))
    
    total_marks = assignment.get('total_marks', 100)
    
    message = f"📊 *Detailed Report: {assignment.get('title')[:30]}*\n\n"
    message += f"Total Marks: {total_marks}\n\n"
    
    # Score distribution
    score_ranges = {'A (≥80%)': 0, 'B (60-79%)': 0, 'C (40-59%)': 0, 'D (<40%)': 0, 'Ungraded': 0}
    
    for sub in submissions:
        marks = sub.get('final_marks')
        if marks is None:
            score_ranges['Ungraded'] += 1
        else:
            pct = (marks / total_marks * 100) if total_marks > 0 else 0
            if pct >= 80:
                score_ranges['A (≥80%)'] += 1
            elif pct >= 60:
                score_ranges['B (60-79%)'] += 1
            elif pct >= 40:
                score_ranges['C (40-59%)'] += 1
            else:
                score_ranges['D (<40%)'] += 1
    
    message += "*Score Distribution:*\n"
    for grade, count in score_ranges.items():
        bar = '█' * min(count, 10)
        message += f"  {grade}: {bar} {count}\n"
    
    message += "\n*Top Performers:*\n"
    graded = [s for s in submissions if s.get('final_marks') is not None]
    for sub in graded[:5]:
        student = db.students.find_one({'student_id': sub['student_id']})
        name = student.get('name', 'Unknown')[:15] if student else 'Unknown'
        message += f"  🏆 {name}: {sub['final_marks']}/{total_marks}\n"
    
    if len([s for s in submissions if s.get('final_marks') is None]) > 0:
        message += "\n*Needs Attention:*\n"
        for sub in submissions:
            if sub.get('final_marks') is None:
                student = db.students.find_one({'student_id': sub['student_id']})
                name = student.get('name', 'Unknown')[:15] if student else 'Unknown'
                message += f"  ⏳ {name}: Awaiting review\n"
    
    keyboard = [
        [InlineKeyboardButton("📥 Download PDF", callback_data=f"pdf_{assignment_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"assign_{assignment_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def pdf_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send PDF report for assignment"""
    query = update.callback_query
    await query.answer("Generating PDF report...")
    
    assignment_id = query.data.replace('pdf_', '')
    
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    assignment = db.assignments.find_one({
        'assignment_id': assignment_id,
        'teacher_id': teacher['teacher_id']
    })
    
    if not assignment:
        await query.edit_message_text("❌ Assignment not found.")
        return
    
    web_url = os.getenv('WEB_URL', 'http://localhost:5000')
    
    # Send download link
    await query.edit_message_text(
        f"📥 *PDF Report Ready*\n\n"
        f"Assignment: {assignment.get('title')}\n\n"
        f"🔗 [Download Full Report]({web_url}/teacher/assignment/{assignment_id}/report)\n\n"
        "_Note: Link opens in web browser_",
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

async def back_to_assignments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Go back to assignments list"""
    query = update.callback_query
    await query.answer()
    
    # Trigger the list_assignments logic
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    assignments = list(db.assignments.find({
        'teacher_id': teacher['teacher_id'],
        'status': 'published'
    }).sort('created_at', -1).limit(10))
    
    keyboard = []
    for a in assignments:
        total_submissions = db.submissions.count_documents({
            'assignment_id': a['assignment_id'],
            'status': {'$in': ['submitted', 'ai_reviewed', 'reviewed']}
        })
        reviewed = db.submissions.count_documents({
            'assignment_id': a['assignment_id'],
            'status': 'reviewed'
        })
        
        label = f"📝 {a.get('title', 'Untitled')[:30]} ({reviewed}/{total_submissions})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"assign_{a['assignment_id']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📚 *Your Assignments*\n\n"
        "Select an assignment to view summary:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick summary command - same as /assignments"""
    await list_assignments(update, context)

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show report download options"""
    if db is None:
        await update.message.reply_text("❌ Database not connected.")
        return
    
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    if not teacher:
        await update.message.reply_text("⚠️ Not linked. Use `/verify <teacher_id>`", parse_mode='Markdown')
        return
    
    assignments = list(db.assignments.find({
        'teacher_id': teacher['teacher_id'],
        'status': 'published'
    }).sort('created_at', -1).limit(10))
    
    if not assignments:
        await update.message.reply_text("📚 No assignments yet.")
        return
    
    keyboard = []
    for a in assignments:
        label = f"📥 {a.get('title', 'Untitled')[:35]}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"pdf_{a['assignment_id']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📥 *Download PDF Report*\n\n"
        "Select an assignment:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def messages_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show student conversations with reply options"""
    if db is None:
        await update.message.reply_text("❌ Database not connected.")
        return
    
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    if not teacher:
        await update.message.reply_text("⚠️ Not linked. Use `/verify <teacher_id>`", parse_mode='Markdown')
        return
    
    # Get students with recent messages
    pipeline = [
        {'$match': {'teacher_id': teacher['teacher_id']}},
        {'$sort': {'timestamp': -1}},
        {'$group': {
            '_id': '$student_id',
            'last_message': {'$first': '$message'},
            'last_time': {'$first': '$timestamp'},
            'from_student': {'$first': '$from_student'},
            'unread': {'$sum': {'$cond': [{'$and': [{'$eq': ['$from_student', True]}, {'$eq': ['$read', False]}]}, 1, 0]}}
        }},
        {'$sort': {'last_time': -1}},
        {'$limit': 10}
    ]
    
    conversations = list(db.messages.aggregate(pipeline))
    
    if not conversations:
        await update.message.reply_text("💬 No conversations yet.\n\nStudents can message you through the web portal.")
        return
    
    # Build inline keyboard for student selection
    keyboard = []
    message_text = "💬 *Your Conversations*\n\n"
    
    for conv in conversations:
        student = db.students.find_one({'student_id': conv['_id']})
        if not student:
            continue
        
        name = student.get('name', 'Unknown')
        student_id = student['student_id']
        unread = conv.get('unread', 0)
        
        # Show preview of last message
        preview = conv.get('last_message', '')[:30] + ('...' if len(conv.get('last_message', '')) > 30 else '')
        direction = '📥' if conv.get('from_student') else '📤'
        unread_badge = f" 🔴{unread}" if unread > 0 else ""
        
        message_text += f"{direction} *{name}*{unread_badge}\n"
        message_text += f"   _{preview}_\n\n"
        
        # Button to reply to this student
        btn_label = f"💬 {name[:20]}" + (f" ({unread})" if unread > 0 else "")
        keyboard.append([InlineKeyboardButton(btn_label, callback_data=f"chat_{student_id}")])
    
    message_text += "_Select a student to reply or use:_\n"
    message_text += "`/reply STUDENT_ID Your message`"
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def chat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle student selection for chat"""
    query = update.callback_query
    await query.answer()
    
    if not query.data.startswith('chat_'):
        return
    
    student_id = query.data.replace('chat_', '')
    
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    student = db.students.find_one({'student_id': student_id})
    
    if not teacher or not student:
        await query.edit_message_text("❌ Error loading conversation.")
        return
    
    # Get recent messages
    messages = list(db.messages.find({
        'student_id': student_id,
        'teacher_id': teacher['teacher_id']
    }).sort('timestamp', -1).limit(10))
    
    messages.reverse()  # Show oldest first
    
    # Mark messages as read
    db.messages.update_many(
        {'student_id': student_id, 'teacher_id': teacher['teacher_id'], 'from_student': True},
        {'$set': {'read': True}}
    )
    
    text = f"💬 *Chat with {student.get('name')}*\n"
    text += f"Student ID: `{student_id}`\n\n"
    
    if messages:
        text += "📜 *Recent Messages:*\n"
        for msg in messages:
            direction = "👤" if msg.get('from_student') else "👨‍🏫"
            time_str = msg.get('timestamp', datetime.utcnow()).strftime('%d/%m %H:%M')
            content = msg.get('message', '')[:100]
            text += f"{direction} _{time_str}_\n{content}\n\n"
    else:
        text += "_No messages yet_\n\n"
    
    text += f"📝 *To reply, use:*\n`/reply {student_id} Your message here`"
    
    keyboard = [
        [InlineKeyboardButton("🗑️ Clear Conversation", callback_data=f"purge_{student_id}")],
        [InlineKeyboardButton("🔙 Back to Messages", callback_data="back_messages")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply to a specific student: /reply STUDENT_ID message"""
    if db is None:
        await update.message.reply_text("❌ Database not connected.")
        return
    
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    if not teacher:
        await update.message.reply_text("⚠️ Not linked. Use `/verify <teacher_id>`", parse_mode='Markdown')
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ *Usage:* `/reply STUDENT_ID Your message`\n\n"
            "Example: `/reply S001 Great work on your assignment!`\n\n"
            "Use /messages to see your conversations.",
            parse_mode='Markdown'
        )
        return
    
    student_id = context.args[0]
    message_text = ' '.join(context.args[1:])
    
    # Find student (case-insensitive)
    student = db.students.find_one({
        'student_id': {'$regex': f'^{re.escape(student_id)}$', '$options': 'i'}
    })
    
    if not student:
        await update.message.reply_text(f"❌ Student `{student_id}` not found.", parse_mode='Markdown')
        return
    
    # Verify teacher is linked to student
    if teacher['teacher_id'] not in student.get('teachers', []):
        await update.message.reply_text(f"⚠️ You are not assigned to this student.")
        return
    
    # Save the message
    db.messages.insert_one({
        'student_id': student['student_id'],
        'teacher_id': teacher['teacher_id'],
        'message': message_text,
        'from_student': False,
        'timestamp': datetime.utcnow(),
        'read': False,
        'sent_via': 'telegram'
    })
    
    await update.message.reply_text(
        f"✅ *Message sent to {student.get('name')}!*\n\n"
        f"_{message_text}_\n\n"
        "They will see it in their web portal.",
        parse_mode='Markdown'
    )

async def purge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Purge conversation with a student: /purge STUDENT_ID"""
    if db is None:
        await update.message.reply_text("❌ Database not connected.")
        return
    
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    
    if not teacher:
        await update.message.reply_text("⚠️ Not linked. Use `/verify <teacher_id>`", parse_mode='Markdown')
        return
    
    if not context.args:
        await update.message.reply_text(
            "⚠️ *Usage:* `/purge STUDENT_ID`\n\n"
            "This will delete all messages with the specified student.\n\n"
            "Use /messages to see your conversations.",
            parse_mode='Markdown'
        )
        return
    
    student_id = context.args[0]
    
    # Find student
    student = db.students.find_one({
        'student_id': {'$regex': f'^{re.escape(student_id)}$', '$options': 'i'}
    })
    
    if not student:
        await update.message.reply_text(f"❌ Student `{student_id}` not found.", parse_mode='Markdown')
        return
    
    # Show confirmation
    keyboard = [
        [InlineKeyboardButton("🗑️ Yes, Delete All", callback_data=f"confirm_purge_{student['student_id']}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_purge")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg_count = db.messages.count_documents({
        'student_id': student['student_id'],
        'teacher_id': teacher['teacher_id']
    })
    
    await update.message.reply_text(
        f"⚠️ *Delete conversation with {student.get('name')}?*\n\n"
        f"This will permanently delete {msg_count} message(s).\n\n"
        "This action cannot be undone.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def purge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle purge confirmation from inline button"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_purge":
        await query.edit_message_text("❌ Cancelled. No messages were deleted.")
        return
    
    if query.data == "back_messages":
        # Redirect to messages command
        chat_id = update.effective_chat.id
        teacher = db.teachers.find_one({'telegram_id': chat_id})
        
        if not teacher:
            await query.edit_message_text("⚠️ Session expired. Use /messages")
            return
        
        # Get conversations (same logic as messages_command)
        pipeline = [
            {'$match': {'teacher_id': teacher['teacher_id']}},
            {'$sort': {'timestamp': -1}},
            {'$group': {
                '_id': '$student_id',
                'last_message': {'$first': '$message'},
                'last_time': {'$first': '$timestamp'},
                'from_student': {'$first': '$from_student'},
                'unread': {'$sum': {'$cond': [{'$and': [{'$eq': ['$from_student', True]}, {'$eq': ['$read', False]}]}, 1, 0]}}
            }},
            {'$sort': {'last_time': -1}},
            {'$limit': 10}
        ]
        
        conversations = list(db.messages.aggregate(pipeline))
        
        keyboard = []
        message_text = "💬 *Your Conversations*\n\n"
        
        for conv in conversations:
            student = db.students.find_one({'student_id': conv['_id']})
            if not student:
                continue
            
            name = student.get('name', 'Unknown')
            student_id = student['student_id']
            unread = conv.get('unread', 0)
            
            preview = conv.get('last_message', '')[:30] + ('...' if len(conv.get('last_message', '')) > 30 else '')
            direction = '📥' if conv.get('from_student') else '📤'
            unread_badge = f" 🔴{unread}" if unread > 0 else ""
            
            message_text += f"{direction} *{name}*{unread_badge}\n"
            message_text += f"   _{preview}_\n\n"
            
            btn_label = f"💬 {name[:20]}" + (f" ({unread})" if unread > 0 else "")
            keyboard.append([InlineKeyboardButton(btn_label, callback_data=f"chat_{student_id}")])
        
        message_text += "_Select a student to reply_"
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    if not query.data.startswith('confirm_purge_') and not query.data.startswith('purge_'):
        return
    
    # Handle purge from chat view (purge_STUDENTID)
    if query.data.startswith('purge_') and not query.data.startswith('purge_confirm'):
        student_id = query.data.replace('purge_', '')
        student = db.students.find_one({'student_id': student_id})
        
        if not student:
            await query.edit_message_text("❌ Student not found.")
            return
        
        chat_id = update.effective_chat.id
        teacher = db.teachers.find_one({'telegram_id': chat_id})
        
        msg_count = db.messages.count_documents({
            'student_id': student_id,
            'teacher_id': teacher['teacher_id']
        })
        
        keyboard = [
            [InlineKeyboardButton("🗑️ Yes, Delete All", callback_data=f"confirm_purge_{student_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="back_messages")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"⚠️ *Delete conversation with {student.get('name')}?*\n\n"
            f"This will permanently delete {msg_count} message(s).\n\n"
            "This action cannot be undone.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Confirmed purge
    student_id = query.data.replace('confirm_purge_', '')
    
    chat_id = update.effective_chat.id
    teacher = db.teachers.find_one({'telegram_id': chat_id})
    student = db.students.find_one({'student_id': student_id})
    
    if not teacher or not student:
        await query.edit_message_text("❌ Error: Could not complete deletion.")
        return
    
    # Delete messages
    result = db.messages.delete_many({
        'student_id': student_id,
        'teacher_id': teacher['teacher_id']
    })
    
    await query.edit_message_text(
        f"✅ *Conversation deleted*\n\n"
        f"Deleted {result.deleted_count} message(s) with {student.get('name')}.",
        parse_mode='Markdown'
    )

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
    if not original_text:
        return
    
    # Extract student info from message formats
    # Format 1: "📱 StudentName: message"
    # Format 2: "📬 New Submission... 👤 Student: Name"
    
    student = None
    
    match = re.search(r'📱\s*([^:]+):', original_text)
    if match:
        student_name = match.group(1).strip()
        student = db.students.find_one({'name': {'$regex': f'^{re.escape(student_name)}', '$options': 'i'}})
    
    if not student:
        match = re.search(r'👤\s*(?:Student:?\s*)?([^\n(]+)', original_text)
        if match:
            student_name = match.group(1).strip()
            student = db.students.find_one({'name': {'$regex': f'^{re.escape(student_name)}', '$options': 'i'}})
    
    if not student:
        await update.message.reply_text("⚠️ Could not identify the student. Please use the web portal to reply.")
        return
    
    reply_text = update.message.text
    
    # Save message
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
        f"✅ Reply sent to *{student.get('name')}*!\n"
        "They will see it in the web portal.",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help"""
    help_text = """📚 *School Portal Bot - Teacher Commands*

*Account:*
/verify <id> - Link your teacher account
/start - Welcome message

*View Data:*
/students - View your students list
/submissions - Pending submissions
/assignments - Assignments with summaries

*Reports:*
/summary - Assignment summary (same as /assignments)
/report - Download PDF report for assignment

*Communication:*
/messages - View conversations with students
/reply <id> <msg> - Reply to a specific student
/purge <id> - Delete conversation with a student

*Quick Reply:*
• Reply directly to any notification to respond
• Or use: `/reply STUDENT_ID Your message`

*Notifications You'll Receive:*
📬 New assignment submissions
📱 Student messages
✅ Review completion alerts

*Web Portal:*
Full features available at the web portal including detailed review interface."""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown commands"""
    await update.message.reply_text("❓ Unknown command. Use /help")

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
    application.add_handler(CommandHandler("assignments", list_assignments))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(CommandHandler("messages", messages_command))
    application.add_handler(CommandHandler("reply", reply_command))
    application.add_handler(CommandHandler("purge", purge_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Callback handlers for inline buttons
    application.add_handler(CallbackQueryHandler(assignment_callback, pattern="^assign_"))
    application.add_handler(CallbackQueryHandler(detail_callback, pattern="^detail_"))
    application.add_handler(CallbackQueryHandler(pdf_callback, pattern="^pdf_"))
    application.add_handler(CallbackQueryHandler(back_to_assignments, pattern="^back_assignments"))
    application.add_handler(CallbackQueryHandler(chat_callback, pattern="^chat_"))
    application.add_handler(CallbackQueryHandler(purge_callback, pattern="^purge_|^confirm_purge_|^cancel_purge|^back_messages"))
    
    # Handle teacher replies
    application.add_handler(MessageHandler(
        filters.REPLY & filters.TEXT & ~filters.COMMAND,
        handle_teacher_reply
    ))
    
    # Unknown commands
    application.add_handler(MessageHandler(filters.COMMAND, handle_unknown))
    
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
