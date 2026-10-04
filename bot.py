import asyncio
import re
import sys
import subprocess
import json
import random
import threading
import signal
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import time
from pathlib import Path

try:
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
except ImportError:
    print("Telethon is not installed. Installing it now...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "telethon"])
    from telethon import TelegramClient, events
from telethon import Button

# ============================================================
# CONFIGURATION
# ============================================================

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
# IMPORTANT:
# Put your NEW/REVOKED bot token here locally.
# Do NOT use the token previously posted in chat.
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
HEALTH_PORT = int(os.getenv("PORT", "8000"))
SOURCE_CHAT_ID = -1003707950453
DEST_CHAT_ID = -1004472814944

GUESS_USER_ID = 8790267038
RAIN_USER_ID = 8966963895

# WHITELIST SYSTEM
OWNER_ID = 1051944146
BOT_USER_ID = 6735017411
WHITELIST_DATA_FILE = Path("whitelist_data.json")
DB_DATA_FILE = Path("maze_db.json")

# ACCESS / RENT PRICING
RENT_PRICES = {1: 300, 3: 500, 7: 750}
IST = ZoneInfo("Asia/Kolkata")

# Keep background work lightweight so POT/Rain notification delivery stays priority.
EPHEMERAL_MAX_CONCURRENCY = 8
# Reuse HTTPS connections for lower alert latency without adding background traffic.
_HTTP_TIMEOUT = 5

SOURCE_USERNAME = "maze"

# Session files
USER_SESSION = "maze_monitor"
BOT_SESSION = "maze_notify_bot"

# ============================================================
# TRIGGER PATTERNS
# ============================================================

# Guess games: amounts/numbers are intentionally NOT hard-coded.
GUESS_PATTERNS = (
    "🪙 SPLIT THE POT",
    "🎯 CLOSEST GUESS",
)

# RAIN: points, quantities, hosts, etc. are intentionally dynamic.
RAIN_RE = re.compile(
    r"🌧\s*RAIN!\s*[\d,]+\s*points\b",
    re.IGNORECASE,
)

# ============================================================
# WHITELIST DATA
# ============================================================

def load_whitelist_data():
    default = {"users": {}, "alert_recipient_ids": []}
    if not WHITELIST_DATA_FILE.exists():
        return default.copy()
    try:
        data = json.loads(WHITELIST_DATA_FILE.read_text(encoding="utf-8"))
        users = data.get("users", {})
        if not isinstance(users, dict):
            users = {}
        cached = data.get("alert_recipient_ids", [])
        if not isinstance(cached, list):
            cached = []
        return {"users": users, "alert_recipient_ids": [int(x) for x in cached if str(x).lstrip("-").isdigit()]}
    except Exception:
        return default.copy()


whitelist_data = load_whitelist_data()
WHITELIST_SAVE_LOCK = threading.Lock()


def save_whitelist_data():
    with WHITELIST_SAVE_LOCK:
        temp_file = WHITELIST_DATA_FILE.with_suffix(".tmp")
        temp_file.write_text(json.dumps(whitelist_data, indent=2), encoding="utf-8")
        temp_file.replace(WHITELIST_DATA_FILE)


def load_db_data():
    default = {"pot_hunted": 0, "rain_hunted": 0}
    if not DB_DATA_FILE.exists():
        return default.copy()
    try:
        data = json.loads(DB_DATA_FILE.read_text(encoding="utf-8"))
        return {
            "pot_hunted": max(0, int(data.get("pot_hunted", 0))),
            "rain_hunted": max(0, int(data.get("rain_hunted", 0))),
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return default.copy()


db_data = load_db_data()
DB_SAVE_LOCK = threading.Lock()


def save_db_data():
    with DB_SAVE_LOCK:
        temp_file = DB_DATA_FILE.with_suffix(".tmp")
        temp_file.write_text(json.dumps(db_data, indent=2), encoding="utf-8")
        temp_file.replace(DB_DATA_FILE)


async def save_db_data_async():
    try:
        await asyncio.to_thread(save_db_data)
    except Exception as e:
        print(f"[DB] Async save error: {e}")


def reset_count_data():
    """Reset POT/Rain counters and persist the zero values immediately."""
    db_data["pot_hunted"] = 0
    db_data["rain_hunted"] = 0
    save_db_data()


def user_label(uid, data):
    name = (data.get("name") or f"User {uid}").strip()
    username = (data.get("username") or "").strip()
    return f"{name} (@{username})" if username else name


def upsert_member(uid, name=None, username=None):
    if not uid or uid in (OWNER_ID, BOT_USER_ID):
        return False
    key = str(uid)
    users = whitelist_data["users"]
    old = users.get(key, {})
    new = {
        "name": name or old.get("name") or f"User {uid}",
        "username": username if username is not None else old.get("username", ""),
        "is_member": old.get("is_member", True),
        "whitelisted_until": old.get("whitelisted_until"),
        "whitelist_days": old.get("whitelist_days"),
        "last_seen": old.get("last_seen"),
    }
    changed = new != old
    users[key] = new
    return changed


def ist_now():
    return datetime.now(IST)


def is_whitelisted(uid):
    if uid == OWNER_ID:
        return True
    data = whitelist_data["users"].get(str(uid))
    if not data:
        return False
    expires = data.get("whitelisted_until")
    if not expires:
        return False
    try:
        return datetime.fromisoformat(expires) > ist_now()
    except (ValueError, TypeError):
        return False


def whitelist_expiry_text(uid):
    data = whitelist_data["users"].get(str(uid), {})
    value = data.get("whitelisted_until")
    if not value:
        return "Not active"
    try:
        dt = datetime.fromisoformat(value)
        return dt.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")
    except (ValueError, TypeError):
        return "Not active"


def set_whitelist(uid, days):
    key = str(uid)
    data = whitelist_data["users"].setdefault(key, {
        "name": f"User {uid}",
        "username": "",
        "is_member": True,
        "whitelisted_until": None,
        "whitelist_days": None,
        "last_seen": None,
    })
    # Expiry is stored as an absolute IST-aware timestamp, so it survives restarts.
    # A new plan starts from now; this keeps 1D/3D/7D predictable.
    expiry = ist_now() + timedelta(days=days)
    data["whitelisted_until"] = expiry.isoformat()
    data["whitelist_days"] = days

    # Keep alert recipients in sync immediately. A newly whitelisted user
    # must receive POT/RAIN DM + ephemeral alerts without requiring /scan.
    recipients = set(whitelist_data.get("alert_recipient_ids", []))
    recipients.add(uid)
    recipients.add(OWNER_ID)
    whitelist_data["alert_recipient_ids"] = sorted(int(x) for x in recipients)

    save_whitelist_data()


def remove_whitelist(uid):
    data = whitelist_data["users"].get(str(uid))
    if not data:
        return False
    data["whitelisted_until"] = None
    data["whitelist_days"] = None

    # Remove immediately from the cached alert recipients so no further
    # POT/RAIN DM or ephemeral alert is sent after access is revoked.
    recipients = set(whitelist_data.get("alert_recipient_ids", []))
    recipients.discard(uid)
    whitelist_data["alert_recipient_ids"] = sorted(int(x) for x in recipients)

    save_whitelist_data()
    return True


def mention_user(uid, data):
    label = f"@{data.get('username')}" if data.get("username") else (data.get("name") or f"User {uid}")
    return f'<a href="tg://user?id={uid}">{label}</a>'


async def sync_destination_members():
    """Full destination-group scan. This is called ONLY by /scan.

    The resulting member/whitelist snapshot is cached and reused by POT/Rain
    alerts, so notification delivery never performs another member scan.
    """
    try:
        count = 0
        changed = False
        scanned_ids = set()

        async for member in user_client.iter_participants(DEST_CHAT_ID):
            if getattr(member, "bot", False):
                continue
            uid = getattr(member, "id", None)
            if not uid or uid in (OWNER_ID, BOT_USER_ID):
                continue

            scanned_ids.add(int(uid))
            first = getattr(member, "first_name", "") or ""
            last = getattr(member, "last_name", "") or ""
            name = (first + " " + last).strip() or f"User {uid}"
            username = getattr(member, "username", "") or ""
            key = str(uid)
            old = whitelist_data["users"].get(key, {}).copy()
            if upsert_member(uid, name, username):
                changed = True
            current = whitelist_data["users"].get(key)
            if current is not None:
                current["is_member"] = True
                current["last_seen"] = datetime.now(timezone.utc).isoformat()
                if current != old:
                    changed = True
            count += 1

        # Cache ONLY users that were present in this scan and are currently
        # whitelisted. Owner is always included. No scan is needed on alerts.
        recipients = {uid for uid in scanned_ids if is_whitelisted(uid)}
        recipients.add(OWNER_ID)
        whitelist_data["alert_recipient_ids"] = sorted(recipients)

        save_whitelist_data()

        whitelisted_count = sum(1 for uid in scanned_ids if is_whitelisted(uid))
        non_whitelisted_count = count - whitelisted_count
        print(
            f"[WHITELIST] Scan complete: members={count} | "
            f"whitelisted={whitelisted_count} | non_whitelisted={non_whitelisted_count} | "
            f"alert_recipients={len(recipients)}"
        )
        return count, whitelisted_count, non_whitelisted_count
    except Exception as e:
        print(f"[WHITELIST] Member scan error: {e}")
        return 0, 0, 0


async def register_destination_user(event):
    if event.chat_id != DEST_CHAT_ID or not event.sender_id or event.sender_id in (OWNER_ID, BOT_USER_ID):
        return
    try:
        sender = getattr(event, "sender", None)
        if sender is None or getattr(sender, "bot", False):
            return
        first = getattr(sender, "first_name", "") or ""
        last = getattr(sender, "last_name", "") or ""
        name = (first + " " + last).strip() or f"User {event.sender_id}"
        username = getattr(sender, "username", "") or ""
        key = str(event.sender_id)
        data = whitelist_data["users"].get(key, {})
        old_snapshot = json.dumps(data, sort_keys=True)
        upsert_member(event.sender_id, name, username)
        data = whitelist_data["users"][key]
        data["is_member"] = True
        # Do not rewrite the JSON database for every normal group message.
        new_snapshot = json.dumps(data, sort_keys=True)
        if old_snapshot != new_snapshot:
            save_whitelist_data()
    except Exception as e:
        print(f"[WHITELIST] Registration error: {e}")


async def get_member_info(uid):
    try:
        entity = await bot_client.get_entity(uid)
    except Exception:
        try:
            entity = await user_client.get_entity(uid)
        except Exception:
            return whitelist_data["users"].get(str(uid), {})
    first = getattr(entity, "first_name", "") or ""
    last = getattr(entity, "last_name", "") or ""
    name = (first + " " + last).strip() or f"User {uid}"
    username = getattr(entity, "username", "") or ""
    upsert_member(uid, name, username)
    return whitelist_data["users"].get(str(uid), {})


def build_users_buttons():
    users = whitelist_data["users"]
    active = sum(1 for uid, data in users.items() if uid != str(OWNER_ID) and is_whitelisted(int(uid)))
    non_active = max(0, len([uid for uid in users if uid != str(OWNER_ID)]) - active)
    return [
        [Button.inline(f"✅ Whitelisted ({active})", data="users|white"),
         Button.inline(f"👤 Non-Whitelisted ({non_active})", data="users|nonwhite")]
    ]


def format_user_list(only_whitelisted):
    """Show only display name + username; never show user IDs or access status."""
    rows = []
    for uid, data in whitelist_data["users"].items():
        if uid in (str(OWNER_ID), str(BOT_USER_ID)):
            continue
        active = is_whitelisted(int(uid))
        if active != only_whitelisted:
            continue

        name = (data.get("name") or "").strip()
        username = (data.get("username") or "").strip().lstrip("@")

        if username and name:
            display = f"{name} — @{username}"
        elif username:
            display = f"@{username}"
        elif name:
            display = name
        else:
            continue

        if only_whitelisted:
            rows.append(f"• 🟢 {display} — ✅ Access")
        else:
            rows.append(f"• 🔴 {display} — ❌ No access")

    title = "✅ WHITELISTED USERS" if only_whitelisted else "👤 NON-WHITELISTED USERS"
    if not rows:
        rows = ["• None"]
    return title + "\n\n" + "\n".join(rows)


# Lightweight standard-library HTTP sender. No third-party urllib3 dependency.
# A fresh request is made only when an alert is actually sent; there is no
# background polling or persistent network traffic while idle.

def _send_ephemeral_request(user_id, text):
    import urllib.request
    import urllib.parse

    payload = urllib.parse.urlencode({
        "chat_id": str(DEST_CHAT_ID),
        "text": text,
        "link_preview_options": json.dumps({"is_disabled": True}),
        "ephemeral_message_parameters": json.dumps({
            "receiver_user_id": int(user_id),
        }),
    }).encode("utf-8")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as response:
        response.read()
    return True


async def send_ephemeral_to_user(user_id, text):
    """Send a group-only ephemeral message.

    Uses only Python's standard library, so Termux does not need urllib3.
    No DM, no member scan, no background polling.
    """
    try:
        return await asyncio.to_thread(_send_ephemeral_request, user_id, text)
    except Exception as e:
        print(f"[EPHEMERAL] Failed for {user_id}: {e}")
        return False


async def broadcast_ephemeral(notification):
    """High-priority POT/RAIN delivery.

    For every active whitelisted recipient, the bot first sends a normal DM,
    then immediately sends the group-only ephemeral copy. Recipients are
    handled concurrently; there is no intentional delay, scan, polling, or
    sleep in this alert path.
    """
    cached = whitelist_data.get("alert_recipient_ids", [])
    recipients = [
        int(uid) for uid in cached
        if int(uid) == OWNER_ID or is_whitelisted(int(uid))
    ]

    if OWNER_ID not in recipients:
        recipients.insert(0, OWNER_ID)

    if not recipients:
        print("[ALERT] No cached recipients. Run /scan first.")
        return 0

    semaphore = asyncio.Semaphore(EPHEMERAL_MAX_CONCURRENCY)

    async def deliver(uid):
        async with semaphore:
            dm_ok = False
            ephemeral_ok = False

            # Priority order: normal DM first, then group-only ephemeral.
            try:
                await bot_client.send_message(
                    uid,
                    notification,
                    link_preview=False,
                    silent=False,
                )
                dm_ok = True
                print(f"[DM] Sent to {uid}")
            except Exception as e:
                # A user may not have started the bot yet, so DM can fail.
                # Still attempt the group-only ephemeral delivery.
                print(f"[DM] Failed for {uid}: {e}")

            try:
                ephemeral_ok = await send_ephemeral_to_user(uid, notification)
            except Exception as e:
                print(f"[EPHEMERAL] Failed for {uid}: {e}")

            return dm_ok, ephemeral_ok

    # All recipients run concurrently. Within each recipient, DM is always
    # attempted before the ephemeral message.
    results = await asyncio.gather(
        *(deliver(uid) for uid in recipients),
        return_exceptions=True,
    )

    dm_sent = 0
    ephemeral_sent = 0
    for result in results:
        if isinstance(result, tuple):
            dm_sent += int(result[0])
            ephemeral_sent += int(result[1])

    print(
        f"[ALERT] Priority delivery complete | "
        f"DM: {dm_sent}/{len(recipients)} | "
        f"Ephemeral: {ephemeral_sent}/{len(recipients)}"
    )
    return ephemeral_sent



async def measure_network_status():
    """Lightweight manual network check. No continuous/background speed test."""
    import urllib.request

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"

    def request():
        started = time.perf_counter()
        req = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": "MazeBot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            response.read()
        latency_ms = (time.perf_counter() - started) * 1000

        if latency_ms < 100:
            quality = "Excellent"
        elif latency_ms < 200:
            quality = "Good"
        elif latency_ms < 400:
            quality = "Fair"
        else:
            quality = "Slow"
        return latency_ms, quality

    try:
        return await asyncio.to_thread(request)
    except Exception as e:
        print(f"[PING] Network check error: {e}")
        return None, "Offline / Unreachable"


# ============================================================
# CLIENTS
# ============================================================

TELETHON_SESSION = os.getenv("TELETHON_SESSION", "").strip()
user_client = TelegramClient(StringSession(TELETHON_SESSION), API_ID, API_HASH) if TELETHON_SESSION else TelegramClient(USER_SESSION, API_ID, API_HASH)
bot_client = TelegramClient(BOT_SESSION, API_ID, API_HASH)


def is_source_message(event):
    """Make sure the event is from the exact source chat."""
    return event.chat_id == SOURCE_CHAT_ID


def get_message_link(message):
    """
    Build a public link for @maze.
    """
    return f"https://t.me/{SOURCE_USERNAME}/{message.id}"


def clean_text(text):
    return (text or "").strip()


def is_guess_trigger(text):
    text = clean_text(text)
    normalized = " ".join(text.split()).casefold()
    return any(pattern.casefold() in normalized for pattern in GUESS_PATTERNS)


def is_rain_trigger(text):
    text = clean_text(text)
    # Match the actual Rain header without depending on a specific
    # separator/bullet after the points amount. This handles small
    # formatting changes in the source message.
    normalized = " ".join(text.split())
    return bool(RAIN_RE.search(normalized))


def format_notification(kind, message):
    link = get_message_link(message)
    text = clean_text(message.raw_text)

    if kind == "guess":
        title = "🎯 NEW GUESS GAME"
    else:
        title = "🌧 NEW RAIN"

    return (
        f"{title}\n\n"
        f"{text}\n\n"
        f"🔗 Open in @maze:\n"
        f"{link}"
    )


async def run_spam(message, count):
    """Run spam independently so the command handler never sleeps between sends."""
    try:
        for index in range(count):
            await bot_client.send_message(DEST_CHAT_ID, message, link_preview=False)
            if index < count - 1:
                await asyncio.sleep(random.uniform(0.77, 1.20))
    except Exception as e:
        print(f"[SPAM] Background send error: {e}")


@bot_client.on(events.NewMessage(chats=DEST_CHAT_ID))
async def destination_message_handler(event):
    try:
        text = clean_text(event.raw_text)

        # --------------------------------------------------------
        # OWNER-ONLY /send
        # --------------------------------------------------------
        if text == "/send" or text.startswith("/send "):
            if event.sender_id != OWNER_ID:
                return
            send_text = text[5:].strip()
            reply = await event.get_reply_message() if event.is_reply else None
            if not send_text and not reply:
                await event.reply("❌ /send <message> or reply to a message with /send")
                return
            try:
                await event.delete()
            except Exception:
                pass
            try:
                if reply and not send_text:
                    if reply.media:
                        media = await reply.download_media(file=bytes)
                        if media is None:
                            raise RuntimeError("Could not download replied media")
                        await bot_client.send_file(DEST_CHAT_ID, media, caption=reply.raw_text or None)
                    elif reply.raw_text:
                        await bot_client.send_message(DEST_CHAT_ID, reply.raw_text, link_preview=False)
                    else:
                        raise RuntimeError("Replied message has no sendable text or media")
                else:
                    await bot_client.send_message(DEST_CHAT_ID, send_text, link_preview=False)
            except Exception as e:
                await bot_client.send_message(DEST_CHAT_ID, f"❌ /send failed: {e}", link_preview=False)
            return

        # --------------------------------------------------------
        # OWNER-ONLY /spam
        # --------------------------------------------------------
        if text == "/spam" or text.startswith("/spam "):
            if event.sender_id != OWNER_ID:
                return
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                await event.reply("❌ Usage: /spam <1-20> <message>")
                return
            try:
                count = int(parts[1])
            except ValueError:
                await event.reply("❌ Count must be 1-20")
                return
            if not 1 <= count <= 20:
                await event.reply("❌ Count must be 1-20")
                return
            message = parts[2].strip()
            if not message:
                await event.reply("❌ Message cannot be empty")
                return
            try:
                await event.delete()
            except Exception:
                pass
            asyncio.create_task(run_spam(message, count))
            return

        # --------------------------------------------------------
        # /rent — show whitelist access pricing
        # --------------------------------------------------------
        if text == "/rent":
            await event.reply(
                "💎 WHITELIST ACCESS PLANS\n\n"
                "🔐 Get private POT & RAIN alerts directly inside the group.\n"
                "⚡ Instant alerts • 🎯 POT • 🌧 RAIN\n\n"
                "💰 ACCESS OPTIONS\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🟢 1 Day  →  300 PTS\n"
                "🔵 3 Days →  500 PTS\n"
                "🟣 7 Days →  750 PTS\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "💳 Pay the rent, get access, and grind freely.\n"
                "🔥 Choose your plan and enjoy the hunt!\n\n"
                "📩 After payment, contact the owner to activate your access."
            )
            return

        # --------------------------------------------------------
        # /adduser — owner only; reply to a member or provide ID
        # --------------------------------------------------------
        if text == "/adduser" or text.startswith("/adduser "):
            if event.sender_id != OWNER_ID:
                await event.reply("You aren't worthy.")
                return
            target = None
            parts = text.split()
            if len(parts) >= 2:
                try:
                    target = int(parts[1])
                except ValueError:
                    target = None
            if target is None and event.is_reply:
                reply = await event.get_reply_message()
                target = reply.sender_id if reply else None
            if not target:
                await event.reply("❌ Reply to a user with /adduser or use /adduser <user_id>.")
                return
            if target == OWNER_ID:
                await event.reply("ℹ️ Owner already has full access.")
                return
            data = await get_member_info(target)
            if is_whitelisted(target):
                await event.reply(
                    f"ℹ️ {user_label(str(target), data)} is already added to whitelist.\n\n"
                    f"⏳ Duration: {data.get('whitelist_days', 'Unknown')}D\n"
                    f"📅 Expires: {whitelist_expiry_text(target)}"
                )
                return
            await event.reply(
                f"👤 Add {user_label(str(target), data)} to whitelist\n\nSelect duration:",
                buttons=[[
                    Button.inline("1D", data=f"wladd|1|{target}"),
                    Button.inline("3D", data=f"wladd|3|{target}"),
                    Button.inline("7D", data=f"wladd|7|{target}"),
                ]]
            )
            return

        # --------------------------------------------------------
        # /rmuser — owner only; reply to a member or provide ID
        # --------------------------------------------------------
        if text == "/rmuser" or text.startswith("/rmuser "):
            if event.sender_id != OWNER_ID:
                await event.reply("You aren't worthy.")
                return
            target = None
            parts = text.split()
            if len(parts) >= 2:
                try:
                    target = int(parts[1])
                except ValueError:
                    pass
            if target is None and event.is_reply:
                reply = await event.get_reply_message()
                target = reply.sender_id if reply else None
            if not target:
                await event.reply("❌ Reply to a user with /rmuser or use /rmuser <user_id>.")
                return
            if remove_whitelist(target):
                await event.reply(f"✅ Removed {target} from whitelist.")
            else:
                await event.reply("ℹ️ User was not whitelisted.")
            return

        # --------------------------------------------------------
        # /scan — owner only; manually refresh the destination member registry.
        # This is the ONLY command that performs the full member scan.
        # POT/RAIN alerts never scan members.
        # --------------------------------------------------------
        if text == "/scan":
            if event.sender_id != OWNER_ID:
                return
            started = time.perf_counter()
            scanned, whitelisted_count, non_whitelisted_count = await sync_destination_members()
            elapsed_ms = (time.perf_counter() - started) * 1000
            await event.reply(
                "🔎 SCAN COMPLETE\n\n"
                f"👥 Members scanned: {scanned}\n"
                f"🟢 Whitelisted: {whitelisted_count}\n"
                f"🔴 Non-Whitelisted: {non_whitelisted_count}\n"
                f"⏱️ Scan time: {elapsed_ms:.0f} ms\n\n"
                "⚡ POT/Rain alerts will use this cached scan — no rescan on every alert."
            )
            return

        # --------------------------------------------------------
        # /ping — owner only; lightweight Telegram API latency test
        # --------------------------------------------------------
        if text == "/ping":
            if event.sender_id != OWNER_ID:
                return
            started = time.perf_counter()
            latency, quality = await measure_network_status()
            handler_ms = (time.perf_counter() - started) * 1000

            if latency is None:
                await event.reply(
                    "❌ NETWORK CHECK FAILED\n\n"
                    "📡 Telegram API: Unreachable\n"
                    "🌐 Internet: Check your connection\n"
                    f"🕒 {ist_now().strftime('%d %b %Y, %I:%M:%S %p IST')}"
                )
            else:
                await event.reply(
                    "🏓 NETWORK STATUS ⚡\n\n"
                    f"📡 Telegram API: {latency:.0f} ms\n"
                    f"🌐 Internet: Connected ({quality})\n"
                    f"🧠 Total handler: {handler_ms:.0f} ms\n\n"
                    "⚡ No member scan or background speed test is running.\n"
                    "🔋 Low CPU • Low RAM • Low network usage\n"
                    f"🕒 {ist_now().strftime('%d %b %Y, %I:%M:%S %p IST')}"
                )
            return

        # --------------------------------------------------------
        # /count — total POT and RAIN notifications hunted
        # /count reset — owner-only reset both counters to 0
        # --------------------------------------------------------
        if text == "/count" or text == "/count reset":
            if text == "/count reset":
                if event.sender_id != OWNER_ID:
                    await event.reply("You aren't worthy.")
                    return
                reset_count_data()
                await event.reply(
                    "✅ COUNT RESET\n\n"
                    "🎯 Total Pot: 0\n"
                    "🌧️ Total Rain: 0"
                )
                return

            await event.reply(
                "📊 MAZE COUNT\n\n"
                f"🎯 Total Pot: {db_data['pot_hunted']}\n"
                f"🌧️ Total Rain: {db_data['rain_hunted']}"
            )
            return

        # --------------------------------------------------------
        # /cmnd — command menu
        # --------------------------------------------------------
        if text == "/cmnd":
            await event.reply(
                "🤖 MAZE BOT — COMMAND CENTER\n\n"
                "👥 USER ACCESS\n"
                "• /adduser — Add whitelist access (1D / 3D / 7D)\n"
                "• /rmuser — Remove whitelist access\n"
                "• /users — View Owner / Whitelisted / Non-Whitelisted\n"
                "• /plans — View all user durations & expiry (Owner only)\n"
                "• /rent — View access plans & prices\n• /myplan — Check your whitelist plan\n\n"
                "📊 STATS & MONITORING\n"
                "• /count — POT & RAIN hunt statistics\n• /count reset — Reset both counters (Owner only)\n"
                "• /ping — Bot speed only\n• /scan — Scan group members + refresh alert access\n\n"
                "🛠️ OWNER TOOLS\n"
                "• /send — Send/re-send a message\n"
                "• /spam — Send repeated messages\n\n"
                "⚡ POT & RAIN alerts are delivered with priority.\n"
                "🔐 Whitelist access survives bot restarts."
            )
            return

        # --------------------------------------------------------
        # /myplan — current user's whitelist plan
        # --------------------------------------------------------
        if text == "/myplan":
            uid = event.sender_id
            if uid == OWNER_ID:
                await event.reply(
                    "👑 YOUR PLAN\n\n"
                    "🔐 Owner access\n"
                    "⏳ Duration: Unlimited\n"
                    "📅 Expires: Never"
                )
                return
            data = whitelist_data["users"].get(str(uid), {})
            if is_whitelisted(uid):
                await event.reply(
                    "💎 MY WHITELIST PLAN\n\n"
                    f"⏳ Duration: {data.get('whitelist_days', 'Unknown')}D\n"
                    f"📅 Expires: {whitelist_expiry_text(uid)}\n"
                    "🟢 Status: Active"
                )
            else:
                await event.reply(
                    "💎 MY WHITELIST PLAN\n\n"
                    "🔴 Status: No active plan\n"
                    "📅 Expires: Not active"
                )
            return

        # --------------------------------------------------------
        # /plans — owner only; show all users' duration and expiry
        # --------------------------------------------------------
        if text == "/plans":
            if event.sender_id != OWNER_ID:
                return
            rows = []
            for uid, data in whitelist_data["users"].items():
                if uid in (str(OWNER_ID), str(BOT_USER_ID)):
                    continue
                name = (data.get("name") or f"User {uid}").strip()
                username = (data.get("username") or "").strip().lstrip("@")
                display = f"{name} — @{username}" if username and name else (f"@{username}" if username else name)
                duration = data.get("whitelist_days")
                expiry = data.get("whitelisted_until")
                if duration and expiry:
                    status = "🟢 Active" if is_whitelisted(int(uid)) else "🔴 Expired"
                    rows.append(f"• {display}\n  ⏳ {duration}D | 📅 {whitelist_expiry_text(int(uid))} | {status}")
                else:
                    rows.append(f"• {display}\n  ⏳ No plan | 📅 Not active | 🔴 Inactive")
            if not rows:
                rows = ["• No users found"]
            await event.reply("👥 ALL USER PLANS\n\n" + "\n\n".join(rows))
            return

        # --------------------------------------------------------
        # /users — owner only; buttons show both lists
        # --------------------------------------------------------
        if text == "/users":
            if event.sender_id != OWNER_ID:
                await event.reply("You aren't worthy.")
                return
            await event.reply(
                "👥 USER ACCESS\n\nChoose a list:",
                buttons=build_users_buttons()
            )
            return

        if not text.startswith(("/send", "/spam", "/adduser", "/rmuser", "/users", "/plans", "/myplan", "/ping", "/scan", "/rent", "/count", "/cmnd")):
            asyncio.create_task(register_destination_user(event))

    except Exception as e:
        print(f"[COMMAND] Error: {e}")


@bot_client.on(events.CallbackQuery(chats=DEST_CHAT_ID))
async def whitelist_callback(event):
    try:
        if event.sender_id != OWNER_ID:
            await event.answer("Owner only.", alert=True)
            return
        data = event.data.decode("utf-8", errors="ignore")
        parts = data.split("|")

        if parts[0] == "wladd" and len(parts) == 3:
            days = int(parts[1])
            target = int(parts[2])
            if days not in (1, 3, 7) or target == OWNER_ID:
                await event.answer("Invalid option.", alert=True)
                return
            await get_member_info(target)
            set_whitelist(target, days)
            user = whitelist_data["users"].get(str(target), {})
            await event.edit(
                "✅ WHITELIST ACTIVATED\n\n"
                f"User: {user_label(str(target), user)}\n"
                f"User ID: {target}\n"
                f"Duration: {days}D\n"
                f"Expires: {whitelist_expiry_text(target)}"
            )
            await event.answer(f"{days}D access activated.")
            return

        if parts[0] == "users" and len(parts) == 2:
            if parts[1] == "owner":
                await event.edit(
                    "👑 OWNER\n\n"
                    f"🆔 User ID: {OWNER_ID}\n"
                    "🔐 Full bot access\n"
                    "⚡ Notification priority: ON",
                    buttons=[[Button.inline("⬅️ Back", data="users|back")]]
                )
                await event.answer()
                return
            if parts[1] not in ("white", "nonwhite"):
                await event.answer("Invalid list.", alert=True)
                return
            only_white = parts[1] == "white"
            await event.edit(format_user_list(only_white))
            await event.answer()
            return

        if parts[0] == "users" and parts[1] == "back":
            await event.edit("👥 USER ACCESS\n\nChoose a list:", buttons=build_users_buttons())
            await event.answer()
            return

        await event.answer("Invalid button.", alert=True)
    except Exception as e:
        print(f"[WHITELIST] Button error: {e}")
        try:
            await event.answer("Something went wrong.", alert=True)
        except Exception:
            pass


@user_client.on(events.NewMessage(chats=SOURCE_CHAT_ID))
async def source_message_handler(event):
    try:
        if not is_source_message(event):
            return

        message = event.message
        text = clean_text(message.raw_text)

        # ----------------------------------------------------
        # GUESS GAME
        # ----------------------------------------------------
        if message.sender_id == GUESS_USER_ID and is_guess_trigger(text):
            notification = format_notification("guess", message)

            # Fire delivery immediately; do not block source-event processing.
            asyncio.create_task(broadcast_ephemeral(notification))
            db_data["pot_hunted"] += 1
            asyncio.create_task(save_db_data_async())
            print(
                f"[GUESS] Notification sent | message_id={message.id} | total_pot={db_data['pot_hunted']}"
            )
            return

        # ----------------------------------------------------
        # RAIN
        # ----------------------------------------------------
        if message.sender_id == RAIN_USER_ID:
            if not is_rain_trigger(text):
                print(f"[RAIN] Source message received but trigger format did not match | message_id={message.id} | text={text[:250]!r}")
                return

            notification = format_notification("rain", message)

            # Fire delivery immediately; do not block source-event processing.
            asyncio.create_task(broadcast_ephemeral(notification))
            db_data["rain_hunted"] += 1
            asyncio.create_task(save_db_data_async())
            print(
                f"[RAIN] Notification sent | message_id={message.id} | total_rain={db_data['rain_hunted']}"
            )
            return

    except Exception as e:
        print(f"[ERROR] Processing message: {e}")


async def main():
    if not API_ID or not API_HASH or not BOT_TOKEN:
        print("ERROR: API_ID, API_HASH and BOT_TOKEN must be set.")
        return
    if not TELETHON_SESSION:
        print("ERROR: TELETHON_SESSION is required for Koyeb startup.")
        return
    if BOT_TOKEN == "PASTE_YOUR_NEW_BOT_TOKEN_HERE":
        print()
        print("ERROR: Add your NEW bot token to BOT_TOKEN first.")
        print("The old token should be revoked because it was exposed.")
        print()
        return

    print("Starting bot...")
    from telethon.errors import FloodWaitError

    while True:
        try:
            await bot_client.start(bot_token=BOT_TOKEN)
            break
        except FloodWaitError as e:
            wait_seconds = int(getattr(e, "seconds", 0) or 0)
            print(f"[TELEGRAM] Bot login is rate-limited. Waiting {wait_seconds}s before retry...")
            await asyncio.sleep(wait_seconds)

    print("Starting Telegram user account...")
    await user_client.start()

    me = await user_client.get_me()
    bot_me = await bot_client.get_me()

    print("POT/Rain alerts are posted instantly in the destination group.")

    print()
    print("========================================")
    print("       MAZE NOTIFICATION BOT")
    print("========================================")
    print(f"User account : {me.id}")
    print(f"Bot          : @{bot_me.username}")
    print(f"Source       : {SOURCE_CHAT_ID} (@{SOURCE_USERNAME})")
    print(f"Destination  : {DEST_CHAT_ID}")
    print("----------------------------------------")
    print(f"Guess user   : {GUESS_USER_ID}")
    print(f"Rain user    : {RAIN_USER_ID}")
    print("----------------------------------------")
    # Member scanning is performed only by the owner using /scan.

    print("Monitoring is active...")
    print("Press Ctrl+C to stop.")
    print("========================================")
    print()

    loop = asyncio.get_running_loop()
    shutdown_started = False

    async def shutdown(reason="shutdown"):
        nonlocal shutdown_started
        if shutdown_started:
            return
        shutdown_started = True
        print(f"\n[SHUTDOWN] {reason} — resetting counters to 0...")
        try:
            reset_count_data()
            print("[SHUTDOWN] Total Pot = 0 | Total Rain = 0")
        except Exception as e:
            print(f"[SHUTDOWN] Could not reset counters: {e}")
        try:
            await user_client.disconnect()
        except Exception:
            pass
        try:
            await bot_client.disconnect()
        except Exception:
            pass

    def handle_signal(signum, frame=None):
        try:
            loop.create_task(shutdown(signal.Signals(signum).name))
        except Exception:
            # Final cleanup is also performed in the main finally block.
            pass

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        try:
            signal.signal(sig, handle_signal)
        except (AttributeError, OSError, ValueError):
            pass

    try:
        await asyncio.gather(
            user_client.run_until_disconnected(),
            bot_client.run_until_disconnected(),
        )
    finally:
        # Any normal stop, Ctrl+C, crash/exception, or handled Termux stop
        # leaves the persistent count database at zero.
        try:
            reset_count_data()
            print("[SHUTDOWN] Counters reset: Total Pot = 0 | Total Rain = 0")
        except Exception as e:
            print(f"[SHUTDOWN] Final counter reset failed: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        # Last-resort cleanup for normal Python termination.
        try:
            reset_count_data()
        except Exception:
            pass
