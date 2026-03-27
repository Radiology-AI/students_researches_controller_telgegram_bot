# Research Assignment Bot v2

## What's new in v2
- Bilingual (Arabic + English) — every message appears in both languages
- Free name input — students can type any names freely
- Full audit log — every click and submission records Telegram user ID, @username, full name
- Optional registered pairs — per-operation list of `Name , @username`; if set, unmatched names are rejected
- /logs command — teacher pulls full audit trail per operation

## Quick Setup

1. Get bot token from @BotFather on Telegram
2. Get your user ID from @userinfobot on Telegram
3. Edit the two lines at the top of bot.py:
   BOT_TOKEN  = "your-token-here"
   TEACHER_ID = your_numeric_id
4. Add the bot as admin to your student group
5. Run:
   pip install -r requirements.txt
   python bot.py

## Teacher Commands
/newop       — Create a new operation (wizard)
/ops         — List all operations
/view <id>   — See assignments + who submitted
/logs <id>   — Full audit log for an operation
/endop <id>  — Close an operation
/cancel      — Cancel the wizard

## /newop Wizard
Step 1: Operation name
Step 2: Subjects (one per line)
Step 3: Minimum names per group
Step 4: Add registered pairs? (optional) — format: Name , @username
Step 5: Group link (https://t.me/mygroup or @mygroup)
Step 6: Confirm → bot posts to group

## Registered Pairs Format (optional)
Ahmed Ali , @ahmed_ali
Sara Hassan , @sara_h
Khalid Omar ,

If you attach a list, student names must match exactly. Leave @username blank if the student has none.

## Audit Log Actions
OP_CREATED, SUBJECT_CLICKED, NAMES_REJECTED_MIN, NAMES_REJECTED_PAIRS, SUBJECT_REGISTERED, OP_CLOSED

Each row stores: tg_user_id, tg_username, tg_fullname, detail, timestamp

## Database
SQLite file: research.db (auto-created)
Tables: operations, subjects, registered_pairs, groups, audit_log
Open with DB Browser for SQLite: https://sqlitebrowser.org/

## Keep running on Linux
screen -S bot
python bot.py
(Ctrl+A then D to detach)
