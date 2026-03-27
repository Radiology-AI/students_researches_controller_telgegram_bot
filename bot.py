"""
Research Assignment Telegram Bot — v2
======================================
Teacher commands (private chat with bot):
  /newop       — Create a new operation
  /ops         — List all operations
  /view <id>   — View group assignments + submitter info
  /logs <id>   — Full audit log for an operation
  /endop <id>  — Close an operation
  /cancel      — Cancel current wizard

Students interact in the group via inline buttons.
"""

import logging
import sqlite3
import json
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
import telegram_lists

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG  — edit these two lines before running
# ══════════════════════════════════════════════════════════════════════════════
BOT_TOKEN  = "8792336911:AAHAB_oBHXY9bz9bNLyWiLc8rgDG8yw9p_Y"
TEACHER_ID = 92200068          # your numeric Telegram user ID
DB_PATH    = "research.db"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Bilingual string table ────────────────────────────────────────────────────
T = {
    # teacher wizard
    "newop_start": (
        "🆕 *عملية جديدة / New Operation*\n\n"
        "ما اسم هذه العملية؟\n"
        "What is the name of this operation?"
    ),
    "ask_subjects": (
        "📚 أدخل *موضوعات البحث* (موضوع واحد في كل سطر):\n"
        "Enter *research subjects* (one per line):\n\n"
        "مثال / Example:\n"
        "`Machine Learning\nData Mining\nCloud Computing`"
    ),
    "subjects_saved": lambda n: (
        f"✅ تم حفظ {n} موضوع. / {n} subjects saved.\n\n"
        "🔢 ما الحد الأدنى لعدد أسماء الطلاب لكل مجموعة؟\n"
        "What is the *minimum* number of student names required per group?"
    ),
    "bad_min": (
        "❗ أدخل رقماً صحيحاً (≥ 1).\n"
        "❗ Please enter a valid number (≥ 1)."
    ),
    "ask_use_pairs": (
        "📋 هل تريد إضافة قائمة مُسجَّلة من أزواج (اسم ↔ معرّف تيليغرام)؟\n"
        "Do you want to add a pre-registered list of (Name ↔ @username) pairs?\n\n"
        "إذا أضفتها، ستُرفض الأسماء التي لا تطابقها.\n"
        "If added, names not on the list will be rejected."
    ),
    "pairs_btn_yes": "✅ نعم / Yes",
    "pairs_btn_no":  "❌ لا / No",
    "ask_pairs": (
        "📋 أرسل قائمة الأزواج، كلٌّ في سطر، بصيغة:\n"
        "Send the list of pairs, one per line, in the format:\n\n"
        "`اسم الطالب , @username`\n\n"
        "مثال / Example:\n"
        "`أحمد علي , @ahmed_ali`\n"
        "`Sara Hassan , @sara_h`"
    ),
    "pairs_bad": (
        "❗ لم يُعثر على أزواج صالحة. أعد المحاولة.\n"
        "❗ No valid pairs found. Try again:"
    ),
    "pairs_saved": lambda n: (
        f"✅ تم حفظ {n} زوج. / {n} pairs saved.\n\n"
        "🔗 أرسل رابط مجموعة التيليغرام:\n"
        "Paste the Telegram group link:"
    ),
    "ask_group": (
        "🔗 أرسل رابط مجموعة التيليغرام (مثال: https://t.me/mygroup أو @mygroup):\n"
        "Paste the Telegram group link (e.g. https://t.me/mygroup or @mygroup):"
    ),
    "confirm_op": lambda d: (
        "📝 *مراجعة / Review*\n\n"
        f"الاسم / Name: *{d['op_name']}*\n"
        "الموضوعات / Subjects:\n" +
        "\n".join(f"  • {s}" for s in d["subjects"]) +
        f"\n\nالحد الأدنى / Min per group: *{d['min_students']}*\n"
        f"قائمة مُسجَّلة / Registered list: *{'نعم / Yes — ' + str(len(d.get('pairs') or [])) + ' pairs' if d.get('pairs') else 'لا / No'}*\n"
        f"المجموعة / Group: {d['group_link']}"
    ),
    "confirm_btn_yes": "✅ تأكيد ونشر / Confirm & Post",
    "confirm_btn_no":  "❌ إلغاء / Cancel",
    "op_posted": lambda name, gid, oid: (
        f"✅ العملية *{name}* (ID: `{oid}`) نُشرت في {gid}!\n"
        f"✅ Operation *{name}* (ID: `{oid}`) posted to {gid}!"
    ),
    "op_saved_no_post": lambda oid, e: (
        f"⚠️ تم الحفظ (ID `{oid}`) لكن تعذّر النشر:\n`{e}`\n\n"
        f"⚠️ Saved (ID `{oid}`) but couldn't post to group:\n`{e}`\n\n"
        "تأكد من أن البوت عضو/مشرف في المجموعة.\n"
        "Make sure the bot is a member/admin of the group."
    ),
    "cancelled": "❌ تم الإلغاء. / Cancelled.",
    # group post
    "group_post": lambda name, min_s: (
        f"📢 *{name}*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📖 تسجيل مواضيع البحث / Research Assignment\n\n"
        "اختر موضوعاً لمجموعتك بالضغط عليه 👇\n"
        "Tap a subject to claim it for your group 👇\n\n"
        f"الحد الأدنى للأسماء: *{min_s}*  |  Min names: *{min_s}*"
    ),
    "all_taken": lambda name: (
        f"📢 *{name}*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✅ تم توزيع جميع المواضيع! 🎉\n"
        "✅ All subjects have been claimed! 🎉"
    ),
    # student flow
    "subject_picked": lambda mention, title, min_s: (
        f"📝 {mention}، اخترت / you selected: *{title}*\n\n"
        f"أرسل أسماء جميع أعضاء المجموعة (الحد الأدنى {min_s})، اسم في كل سطر:\n"
        f"Send all group member names (min {min_s}), one name per line:"
    ),
    "op_closed_alert":     "🔴 هذه العملية مغلقة. / This operation is closed.",
    "already_taken_alert": "⚠️ هذا الموضوع محجوز! اختر آخر. / Subject already taken!",
    "not_enough_names": lambda got, need: (
        f"❗ أدخلت {got} اسم(اً)، المطلوب على الأقل {need}.\n"
        f"❗ You entered {got} name(s); at least {need} required.\n"
        "أعد الإرسال. / Please resend:"
    ),
    "invalid_names": lambda bads: (
        "❌ هذه الأسماء غير موجودة في القائمة المُسجَّلة:\n"
        "❌ These names are not in the registered list:\n" +
        "\n".join(f"  • {n}" for n in bads) +
        "\n\nصحّح وأعد الإرسال. / Please correct and resend:"
    ),
    "assigned_ok": lambda title, names: (
        f"✅ تم تسجيل *{title}* للمجموعة:\n"
        f"✅ *{title}* assigned to:\n"
        f"👥 {', '.join(names)}\n\n"
        "بالتوفيق! 🎓 / Good luck! 🎓"
    ),
    # teacher view / log
    "op_not_found":  "❌ العملية غير موجودة. / Operation not found.",
    "no_groups_yet": "_لا توجد مجموعات مُسجَّلة بعد. / No groups registered yet._",
    "no_ops": (
        "لا توجد عمليات بعد. استخدم /newop لإنشاء واحدة.\n"
        "No operations yet. Use /newop."
    ),
    "endop_done": lambda oid: (
        f"🔴 العملية `{oid}` مغلقة الآن. / Operation `{oid}` is now closed."
    ),
    "only_teacher": "⛔ هذا الأمر للأستاذ فقط. / Only the teacher can use this.",
    "usage_view":   "الاستخدام / Usage: /view <operation_id>",
    "usage_endop":  "الاستخدام / Usage: /endop <operation_id>",
    "usage_logs":   "الاستخدام / Usage: /logs <operation_id>",
    "teacher_start": (
        "👋 مرحباً أستاذ! / Welcome, Professor!\n\n"
        "الأوامر / Commands:\n"
        "• /newop — عملية جديدة / New operation\n"
        "• /ops — قائمة العمليات / List operations\n"
        "• /view <id> — عرض التسجيلات / View assignments\n"
        "• /logs <id> — سجل التدقيق / Full audit log\n"
        "• /endop <id> — إغلاق عملية / Close operation\n"
        "• /cancel — إلغاء / Cancel current wizard"
    ),
    "student_start": (
        "👋 مرحباً! / Welcome!\n"
        "تحقق من المجموعة لاختيار موضوع بحثك.\n"
        "Check the group to claim a research subject."
    ),
}

# ── Conversation states ────────────────────────────────────────────────────────
(
    OP_NAME, OP_SUBJECTS, OP_MIN_STUDENTS,
    OP_WANT_PAIRS, OP_PAIRS,
    OP_GROUP_LINK, OP_CONFIRM,
    STUDENT_NAMES,
) = range(8)


# ══════════════════════════════════════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════════════════════════════════════

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS operations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT    NOT NULL,
            group_chat_id   TEXT,
            group_msg_id    TEXT,
            group_link      TEXT,
            min_students    INTEGER DEFAULT 1,
            active          INTEGER DEFAULT 1,
            created_at      TEXT
        );

        -- Optional name↔username pairs per operation
        CREATE TABLE IF NOT EXISTS registered_pairs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            op_id       INTEGER NOT NULL,
            full_name   TEXT    NOT NULL,
            tg_username TEXT,
            FOREIGN KEY (op_id) REFERENCES operations(id)
        );

        CREATE TABLE IF NOT EXISTS subjects (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            op_id   INTEGER NOT NULL,
            title   TEXT    NOT NULL,
            taken   INTEGER DEFAULT 0,
            FOREIGN KEY (op_id) REFERENCES operations(id)
        );

        -- Groups assigned to subjects
        CREATE TABLE IF NOT EXISTS groups (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            op_id           INTEGER NOT NULL,
            subject_id      INTEGER NOT NULL,
            student_names   TEXT    NOT NULL,   -- JSON array
            submitted_by_id TEXT    NOT NULL,   -- Telegram user_id
            submitted_by_un TEXT,               -- @username (may be empty)
            submitted_by_fn TEXT,               -- full name
            submitted_at    TEXT,
            FOREIGN KEY (op_id)      REFERENCES operations(id),
            FOREIGN KEY (subject_id) REFERENCES subjects(id)
        );

        -- Every significant action is recorded here
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            op_id       INTEGER NOT NULL,
            subject_id  INTEGER,
            action      TEXT    NOT NULL,
            tg_user_id  TEXT,
            tg_username TEXT,
            tg_fullname TEXT,
            detail      TEXT,
            happened_at TEXT,
            FOREIGN KEY (op_id) REFERENCES operations(id)
        );
    """)
    con.commit()
    con.close()


def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def log_action(op_id, subject_id, action, user, detail=""):
    """Append a row to the audit_log table."""
    con = get_db()
    con.execute(
        "INSERT INTO audit_log "
        "(op_id, subject_id, action, tg_user_id, tg_username, tg_fullname, detail, happened_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            op_id, subject_id, action,
            str(user.id),
            user.username or "",
            user.full_name or "",
            detail,
            datetime.now().isoformat(),
        ),
    )
    con.commit()
    con.close()


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def is_teacher(uid: int) -> bool:
    return uid == TEACHER_ID


def subjects_keyboard(op_id: int):
    """Return an InlineKeyboardMarkup of untaken subjects, or None if all taken."""
    con = get_db()
    rows = con.execute(
        "SELECT id, title FROM subjects WHERE op_id=? AND taken=0", (op_id,)
    ).fetchall()
    con.close()
    if not rows:
        return None
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(r["title"], callback_data=f"pick|{op_id}|{r['id']}")]
        for r in rows
    ])


def format_operation_summary(op_id: int) -> str:
    con = get_db()
    op = con.execute(
        "SELECT name, min_students, active FROM operations WHERE id=?", (op_id,)
    ).fetchone()
    if not op:
        con.close()
        return T["op_not_found"]

    status = "🟢 نشطة/Active" if op["active"] else "🔴 مغلقة/Closed"
    lines = [
        f"📋 *{op['name']}* — {status}",
        f"الحد الأدنى / Min per group: {op['min_students']}",
        "",
    ]
    groups = con.execute(
        """SELECT s.title,
                  g.student_names,
                  g.submitted_by_un,
                  g.submitted_by_fn,
                  g.submitted_by_id,
                  g.submitted_at
           FROM groups g
           JOIN subjects s ON s.id = g.subject_id
           WHERE g.op_id=?
           ORDER BY g.submitted_at""",
        (op_id,),
    ).fetchall()
    con.close()

    if groups:
        for g in groups:
            names = ", ".join(json.loads(g["student_names"]))
            who   = f"@{g['submitted_by_un']}" if g["submitted_by_un"] else g["submitted_by_fn"]
            lines += [
                f"▪ *{g['title']}*",
                f"  👥 {names}",
                f"  🪵 {who} (ID: `{g['submitted_by_id']}`) — {g['submitted_at'][:16]}\n",
            ]
    else:
        lines.append(T["no_groups_yet"])
    return "\n".join(lines)


def format_audit_log(op_id: int) -> str:
    con = get_db()
    op = con.execute("SELECT name FROM operations WHERE id=?", (op_id,)).fetchone()
    if not op:
        con.close()
        return T["op_not_found"]
    rows = con.execute(
        "SELECT action, tg_username, tg_fullname, tg_user_id, detail, happened_at "
        "FROM audit_log WHERE op_id=? ORDER BY happened_at",
        (op_id,),
    ).fetchall()
    con.close()

    lines = [f"🪵 *سجل التدقيق / Audit Log — {op['name']}*\n"]
    if not rows:
        lines.append("_لا توجد أحداث. / No events yet._")
    else:
        for r in rows:
            who = f"@{r['tg_username']}" if r["tg_username"] else r["tg_fullname"]
            lines.append(
                f"`{r['happened_at'][:16]}` *{r['action']}*\n"
                f"  👤 {who} (ID: `{r['tg_user_id']}`)\n"
                f"  📄 {r['detail']}\n"
            )
    return "\n".join(lines)


def parse_pairs(text: str):
    """Parse 'Name , @username' lines → list of (full_name, tg_username)."""
    pairs = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if "," in line:
            parts = line.split(",", 1)
            name = parts[0].strip()
            un   = parts[1].strip().lstrip("@")
        else:
            name, un = line, ""
        if name:
            pairs.append((name, un))
    return pairs


def validate_names_against_pairs(op_id: int, names: list) -> list:
    """Return names not found in registered_pairs for this operation."""
    con = get_db()
    registered = [
        r["full_name"]
        for r in con.execute(
            "SELECT full_name FROM registered_pairs WHERE op_id=?", (op_id,)
        ).fetchall()
    ]
    con.close()
    if not registered:
        return []   # no list → accept everything
    return [n for n in names if n not in registered]


# ══════════════════════════════════════════════════════════════════════════════
# TEACHER CONVERSATION — /newop wizard
# ══════════════════════════════════════════════════════════════════════════════

async def newop_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_teacher(update.effective_user.id):
        await update.message.reply_text(T["only_teacher"])
        return ConversationHandler.END
    ctx.user_data.clear()
    await update.message.reply_text(T["newop_start"], parse_mode="Markdown")
    return OP_NAME


async def op_got_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["op_name"] = update.message.text.strip()
    await update.message.reply_text(T["ask_subjects"], parse_mode="Markdown")
    return OP_SUBJECTS


async def op_got_subjects(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    subjects = [s.strip() for s in update.message.text.strip().splitlines() if s.strip()]
    if not subjects:
        await update.message.reply_text(
            "❗ أدخل موضوعاً واحداً على الأقل. / Enter at least one subject."
        )
        return OP_SUBJECTS
    ctx.user_data["subjects"] = subjects
    await update.message.reply_text(T["subjects_saved"](len(subjects)), parse_mode="Markdown")
    return OP_MIN_STUDENTS


async def op_got_min(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        n = int(update.message.text.strip())
        assert n >= 1
    except Exception:
        await update.message.reply_text(T["bad_min"])
        return OP_MIN_STUDENTS
    ctx.user_data["min_students"] = n
    ctx.user_data["pairs"] = None

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(T["pairs_btn_yes"], callback_data="pairs|yes")],
        [InlineKeyboardButton(T["pairs_btn_no"],  callback_data="pairs|no")],
    ])
    await update.message.reply_text(T["ask_use_pairs"], parse_mode="Markdown", reply_markup=kb)
    return OP_WANT_PAIRS


async def op_want_pairs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "pairs|yes":
        await query.message.reply_text(T["ask_pairs"], parse_mode="Markdown")
        return OP_PAIRS
    ctx.user_data["pairs"] = []
    await query.message.reply_text(T["ask_group"], parse_mode="Markdown")
    return OP_GROUP_LINK


async def op_got_pairs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pairs = parse_pairs(update.message.text)
    if not pairs:
        await update.message.reply_text(T["pairs_bad"])
        return OP_PAIRS
    ctx.user_data["pairs"] = pairs
    await update.message.reply_text(T["pairs_saved"](len(pairs)), parse_mode="Markdown")
    return OP_GROUP_LINK


async def op_got_group(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["group_link"] = update.message.text.strip()
    summary = T["confirm_op"](ctx.user_data)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(T["confirm_btn_yes"], callback_data="confirm|yes")],
        [InlineKeyboardButton(T["confirm_btn_no"],  callback_data="confirm|no")],
    ])
    await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=kb)
    return OP_CONFIRM


async def op_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm|no":
        await query.message.reply_text(T["cancelled"])
        return ConversationHandler.END

    data = ctx.user_data
    now  = datetime.now().isoformat()
    con  = get_db()

    cur = con.execute(
        "INSERT INTO operations (name, group_link, min_students, active, created_at) "
        "VALUES (?,?,?,1,?)",
        (data["op_name"], data["group_link"], data["min_students"], now),
    )
    op_id = cur.lastrowid

    for s in data["subjects"]:
        con.execute("INSERT INTO subjects (op_id, title, taken) VALUES (?,?,0)", (op_id, s))

    for full_name, tg_un in (data.get("pairs") or []):
        con.execute(
            "INSERT INTO registered_pairs (op_id, full_name, tg_username) VALUES (?,?,?)",
            (op_id, full_name, tg_un),
        )

    con.commit()
    con.close()

    log_action(
        op_id, None, "OP_CREATED", update.effective_user,
        f"subjects={len(data['subjects'])}, pairs={len(data.get('pairs') or [])}",
    )

    # Derive a chat identifier from the link
    link = data["group_link"]
    if "t.me/" in link:
        group_target = "@" + link.split("t.me/")[-1].split("/")[0]
    elif link.startswith("@"):
        group_target = link
    else:
        group_target = "@" + link

    kb  = subjects_keyboard(op_id)
    msg = T["group_post"](data["op_name"], data["min_students"])

    try:
        sent = await query.get_bot().send_message(
            chat_id=group_target,
            text=msg,
            parse_mode="Markdown",
            reply_markup=kb,
        )
        con = get_db()
        con.execute(
            "UPDATE operations SET group_chat_id=?, group_msg_id=? WHERE id=?",
            (str(sent.chat_id), str(sent.message_id), op_id),
        )
        con.commit()
        con.close()
        await query.message.reply_text(
            T["op_posted"](data["op_name"], group_target, op_id),
            parse_mode="Markdown",
        )
    except Exception as e:
        await query.message.reply_text(
            T["op_saved_no_post"](op_id, e), parse_mode="Markdown"
        )

    return ConversationHandler.END


async def op_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(T["cancelled"])
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════════════════════
# STUDENT FLOW — pick subject → send names
# ══════════════════════════════════════════════════════════════════════════════

async def subject_picked(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    _, op_id_s, subj_id_s = query.data.split("|")
    op_id, subject_id = int(op_id_s), int(subj_id_s)

    con  = get_db()
    op   = con.execute(
        "SELECT min_students, active, name FROM operations WHERE id=?", (op_id,)
    ).fetchone()
    subj = con.execute(
        "SELECT title, taken FROM subjects WHERE id=?", (subject_id,)
    ).fetchone()
    pair_count = con.execute(
        "SELECT COUNT(*) AS c FROM registered_pairs WHERE op_id=?", (op_id,)
    ).fetchone()["c"]
    con.close()

    if not op or not subj:
        await query.answer("❌", show_alert=True)
        return ConversationHandler.END

    if not op["active"]:
        await query.answer(T["op_closed_alert"], show_alert=True)
        return ConversationHandler.END

    if subj["taken"]:
        await query.answer(T["already_taken_alert"], show_alert=True)
        return ConversationHandler.END

    await query.answer()

    user    = query.from_user
    mention = f"@{user.username}" if user.username else user.full_name

    ctx.user_data["pending"] = {
        "op_id":      op_id,
        "subject_id": subject_id,
        "min_s":      op["min_students"],
        "has_pairs":  pair_count > 0,
        "title":      subj["title"],
        "op_name":    op["name"],
        "chat_id":    query.message.chat_id,
        "msg_id":     query.message.message_id,
    }

    log_action(op_id, subject_id, "SUBJECT_CLICKED", user,
               f"subject='{subj['title']}'")

    await query.message.reply_text(
        T["subject_picked"](mention, subj["title"], op["min_students"]),
        parse_mode="Markdown",
    )
    return STUDENT_NAMES


async def student_names_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pending = ctx.user_data.get("pending")
    if not pending:
        return ConversationHandler.END

    user  = update.effective_user
    names = [n.strip() for n in update.message.text.strip().splitlines() if n.strip()]
    min_s = pending["min_s"]

    # ── minimum count check ───────────────────────────────────────────────────
    if len(names) < min_s:
        log_action(pending["op_id"], pending["subject_id"],
                   "NAMES_REJECTED_MIN", user,
                   f"got={len(names)}, need={min_s}")
        await update.message.reply_text(
            T["not_enough_names"](len(names), min_s), parse_mode="Markdown"
        )
        return STUDENT_NAMES

    # ── registered-pairs check (only if a list was set for this op) ───────────
    if pending["has_pairs"]:
        invalid = validate_names_against_pairs(pending["op_id"], names)
        if invalid:
            log_action(pending["op_id"], pending["subject_id"],
                       "NAMES_REJECTED_PAIRS", user,
                       f"invalid={invalid}")
            await update.message.reply_text(
                T["invalid_names"](invalid), parse_mode="Markdown"
            )
            return STUDENT_NAMES

    # ── save assignment ───────────────────────────────────────────────────────
    now = datetime.now().isoformat()
    con = get_db()
    con.execute(
        "INSERT INTO groups "
        "(op_id, subject_id, student_names, submitted_by_id, submitted_by_un, submitted_by_fn, submitted_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            pending["op_id"],
            pending["subject_id"],
            json.dumps(names, ensure_ascii=False),
            str(user.id),
            user.username or "",
            user.full_name or "",
            now,
        ),
    )
    con.execute("UPDATE subjects SET taken=1 WHERE id=?", (pending["subject_id"],))
    con.commit()
    con.close()

    log_action(
        pending["op_id"], pending["subject_id"],
        "SUBJECT_REGISTERED", user,
        f"subject='{pending['title']}', names={names}",
    )

    await update.message.reply_text(
        T["assigned_ok"](pending["title"], names), parse_mode="Markdown"
    )

    # ── update the group message (remove taken subject button) ────────────────
    kb  = subjects_keyboard(pending["op_id"])
    bot = update.get_bot()
    try:
        if kb:
            await bot.edit_message_reply_markup(
                chat_id=pending["chat_id"],
                message_id=pending["msg_id"],
                reply_markup=kb,
            )
        else:
            await bot.edit_message_text(
                chat_id=pending["chat_id"],
                message_id=pending["msg_id"],
                text=T["all_taken"](pending["op_name"]),
                parse_mode="Markdown",
            )
    except Exception:
        pass   # message may already be edited by another concurrent update

    ctx.user_data.pop("pending", None)
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════════════════════
# TEACHER — read-only commands
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if is_teacher(update.effective_user.id):
        await update.message.reply_text(T["teacher_start"])
    else:
        await update.message.reply_text(T["student_start"])


async def cmd_ops(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_teacher(update.effective_user.id):
        await update.message.reply_text(T["only_teacher"])
        return
    con = get_db()
    ops = con.execute(
        "SELECT id, name, active, created_at FROM operations ORDER BY id DESC"
    ).fetchall()
    con.close()

    if not ops:
        await update.message.reply_text(T["no_ops"])
        return

    items = [
        f"{'🟢' if r['active'] else '🔴'} [{r['id']}] {r['name']} — {r['created_at'][:10]}"
        for r in ops
    ]
    text = telegram_lists.bullet_list("📋 العمليات / Operations", items)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_teacher(update.effective_user.id):
        await update.message.reply_text(T["only_teacher"])
        return
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text(T["usage_view"])
        return
    await update.message.reply_text(
        format_operation_summary(int(ctx.args[0])), parse_mode="Markdown"
    )


async def cmd_logs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_teacher(update.effective_user.id):
        await update.message.reply_text(T["only_teacher"])
        return
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text(T["usage_logs"])
        return
    await update.message.reply_text(
        format_audit_log(int(ctx.args[0])), parse_mode="Markdown"
    )


async def cmd_endop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_teacher(update.effective_user.id):
        await update.message.reply_text(T["only_teacher"])
        return
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text(T["usage_endop"])
        return
    op_id = int(ctx.args[0])
    con   = get_db()
    con.execute("UPDATE operations SET active=0 WHERE id=?", (op_id,))
    con.commit()
    con.close()
    log_action(op_id, None, "OP_CLOSED", update.effective_user)
    await update.message.reply_text(T["endop_done"](op_id), parse_mode="Markdown")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    teacher_conv = ConversationHandler(
        entry_points=[CommandHandler("newop", newop_start)],
        states={
            OP_NAME:         [MessageHandler(filters.TEXT & ~filters.COMMAND, op_got_name)],
            OP_SUBJECTS:     [MessageHandler(filters.TEXT & ~filters.COMMAND, op_got_subjects)],
            OP_MIN_STUDENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, op_got_min)],
            OP_WANT_PAIRS:   [CallbackQueryHandler(op_want_pairs, pattern=r"^pairs\|")],
            OP_PAIRS:        [MessageHandler(filters.TEXT & ~filters.COMMAND, op_got_pairs)],
            OP_GROUP_LINK:   [MessageHandler(filters.TEXT & ~filters.COMMAND, op_got_group)],
            OP_CONFIRM:      [CallbackQueryHandler(op_confirm,    pattern=r"^confirm\|")],
        },
        fallbacks=[CommandHandler("cancel", op_cancel)],
    )

    student_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(subject_picked, pattern=r"^pick\|")],
        states={
            STUDENT_NAMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, student_names_received)],
        },
        fallbacks=[],
        per_user=True,
        per_chat=False,
    )

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("ops",    cmd_ops))
    app.add_handler(CommandHandler("view",   cmd_view))
    app.add_handler(CommandHandler("logs",   cmd_logs))
    app.add_handler(CommandHandler("endop",  cmd_endop))
    app.add_handler(teacher_conv)
    app.add_handler(student_conv)

    logger.info("✅ Bot is running…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
