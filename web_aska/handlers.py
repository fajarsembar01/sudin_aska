# web_aska/handlers.py
import asyncio
import os
import time
from typing import Optional
from threading import Lock

from dotenv import load_dotenv
# from openai import OpenAI  # not used in web handler

from ai_core import build_qa_chain
from knowledge_loader import (
    GENERAL_FILE,
    SPECIFIC_FILE,
    DATA_SEKOLAH_FILE,
    DETAIL_SEKOLAH_FILE,
    STRUKTUR_ORG_FILE,
)
from db import save_chat, get_chat_history
from rag_logger import save_rag_log
from responses import ASKA_NO_DATA_RESPONSE, ASKA_TECHNICAL_ISSUE_RESPONSE
from utils import (
    normalize_input,
    now_str,
    format_history_for_chain,
    coerce_to_text,
    rewrite_schedule_query,
    replace_bot_mentions,
    remove_trailing_signature,
)
from flows.safety_flow import handle_bullying
from flows.corruption_flow import handle_corruption
from flows.psych_flow import handle_psych
from flows.teacher_flow import handle_teacher
from flows.smalltalk_flow import handle_smalltalk

# --- Mock Telegram Objects ---
class MockBot:
    def __init__(self, username="ASKA_WEB"):
        self.username = username

    async def send_chat_action(self, chat_id, action):
        # No-op for web environment
        return None

class MockUser:
    def __init__(self, user_id, first_name="WebUser", username=None):
        self.id = user_id
        self.first_name = first_name
        self.username = username if username else first_name

class MockMessage:
    def __init__(self, user, text):
        self.from_user = user
        self.text = text

    # Adapter to capture replies from flow modules
    def _init_capture(self):
        self._last_reply: Optional[str] = None

    async def reply_text(self, text, parse_mode=None):
        # Capture bot reply (keep markdown) but trim signature for web output
        self._last_reply = remove_trailing_signature(text)
        return None

class MockUpdate:
    def __init__(self, message):
        self.message = message
        self.effective_user = message.from_user
        self.effective_chat = self # Simplified for web
        self.id = id(self)

class MockContext:
    def __init__(self, chat_data):
        self._chat_data = chat_data
        self.bot = MockBot()

    @property
    def chat_data(self):
        return self._chat_data

# --- Session Management ---
web_sessions = {}

load_dotenv()
qa_chain = build_qa_chain()
_qa_chain_lock = Lock()
_last_kb_mtime: Optional[float] = None
_last_kb_check_ts: float = 0.0
_KB_CHECK_INTERVAL = float(os.getenv("ASKA_KB_CHECK_INTERVAL", "5") or 5)


def _get_kb_mtime() -> float:
    mtimes = []
    for path in (
        GENERAL_FILE,
        SPECIFIC_FILE,
        DATA_SEKOLAH_FILE,
        DETAIL_SEKOLAH_FILE,
        STRUKTUR_ORG_FILE,
    ):
        try:
            mtimes.append(path.stat().st_mtime)
        except FileNotFoundError:
            continue
    return max(mtimes) if mtimes else 0.0


def _maybe_reload_qa_chain() -> None:
    global _last_kb_mtime, _last_kb_check_ts
    if _KB_CHECK_INTERVAL <= 0:
        return
    now_ts = time.time()
    if (now_ts - _last_kb_check_ts) < _KB_CHECK_INTERVAL:
        return
    _last_kb_check_ts = now_ts
    current_mtime = _get_kb_mtime()
    if _last_kb_mtime is None:
        _last_kb_mtime = current_mtime
        return
    if current_mtime > _last_kb_mtime:
        reload_qa_chain()
        _last_kb_mtime = current_mtime


def reload_qa_chain() -> None:
    """Reload QA chain after knowledge updates."""
    global qa_chain, _last_kb_mtime
    with _qa_chain_lock:
        qa_chain = build_qa_chain()
        _last_kb_mtime = _get_kb_mtime()

TEACHER_CONVERSATION_LIMIT = 10
TEACHER_TIMEOUT_SECONDS = 600
PSYCH_TIMEOUT_SECONDS = 600
BULLYING_TIMEOUT_SECONDS = 600

TEACHER_TIMEOUT_MESSAGE = (
    "Latihan kita ke-pause lumayan lama nih, ASKA pamit dulu ya. "
    "Kalau mau lanjut tinggal panggil ASKA lagi. Sampai jumpa! 😄✨"
)

PSYCH_TIMEOUT_MESSAGE = (
    "Obrolan laporan konselingnya udah sunyi lama, ASKA pamit sementara ya. "
    "Kapan pun butuh cerita lagi langsung chat ASKA. Sampai jumpa! 🤗💖"
)

# Psych severity rank handled inside shared flows (responses/psychologist)

async def process_channel_request(
    user_id: int,
    user_input: str,
    *,
    username: str = "WebUser",
    topic: str = "web",
) -> tuple[str, Optional[int]]:
    """Main function to handle chat request from non-Telegram channels.
    
    Returns:
        tuple: (response_text, chat_log_id) where chat_log_id is the ID of the bot's response
    """
    normalized_topic = (topic or "web").strip().lower()
    if normalized_topic not in {"web", "whatsapp"}:
        normalized_topic = "web"

    session_key = f"{normalized_topic}:{user_id}"
    session_data = web_sessions.setdefault(session_key, {})
    _maybe_reload_qa_chain()

    user = MockUser(user_id, first_name=username)
    message = MockMessage(user, user_input)
    update = MockUpdate(message)
    context = MockContext(session_data)

    response_text = ASKA_TECHNICAL_ISSUE_RESPONSE

    try:
        raw_input = user_input or ""
        bot_username = getattr(context.bot, "username", None)
        raw_input = replace_bot_mentions(raw_input, bot_username)
        normalized_input = normalize_input(raw_input)

        user_obj = user
        # This username is now correctly set from the function parameter
        username = user.username

        print(
            f"[{now_str()}] {normalized_topic.upper()} HANDLER CALLED - FROM {username}: {normalized_input}"
        )

        storage_key = user_id

        recent_messages_root = context.chat_data.setdefault("recent_messages_by_user", {})
        recent_messages = recent_messages_root.setdefault(storage_key, {})
        now_ts = time.time()
        for msg_text, ts in list(recent_messages.items()):
            if (now_ts - ts) > 600:
                del recent_messages[msg_text]
        last_ts = recent_messages.get(normalized_input)
        if last_ts is not None and (now_ts - last_ts) < 60:
            print(f"[{now_str()}] DUPLICATE MESSAGE RECEIVED WITHIN 60s - SKIPPING")
            # Let the user know the duplicate message was treated as spammy noise.
            return (
                "Uh-oh, chat kamu kembar sama yang barusan nih jadi aku skip dulu biar "
                "nggak kebaca spam 😅 Cobain kirim versi beda atau tunggu bentar ya ✨",
                None
            )
        recent_messages[normalized_input] = now_ts

        print(f"[{now_str()}] SAVING USER MESSAGE")
        chat_log_id = save_chat(
            user_id,
            username,
            normalized_input,
            role="user",
            topic=normalized_topic,
        )

        # 1) Bullying / Safety (reuse shared flow)
        reply_target = MockMessage(user, "")
        reply_target._init_capture()
        handled = await handle_bullying(
            update=update,
            context=context,
            reply_message=reply_target,
            raw_input=raw_input,
            normalized_input=normalized_input,
            user_id=user_id,
            username=username,
            chat_log_id=chat_log_id,
            source=normalized_topic,
            mark_responded=lambda: None,
            storage_key=storage_key,
            now_ts=now_ts,
            timeout_seconds=BULLYING_TIMEOUT_SECONDS,
            topic=normalized_topic,
        )
        if handled:
            print(f"[{now_str()}] {normalized_topic.upper()} FLOW HANDLED: bullying")
            return reply_target._last_reply or "", None

        # 2) Corruption Reporting Flow (reuse shared flow)
        reply_target = MockMessage(user, "")
        reply_target._init_capture()
        handled = await handle_corruption(
            update=update,
            context=context,
            reply_message=reply_target,
            raw_input=raw_input,
            normalized_input=normalized_input,
            user_id=user_id,
            username=username,
            storage_key=storage_key,
            source=normalized_topic,
            topic=normalized_topic,
            mark_responded=lambda: None,
        )
        if handled:
            print(f"[{now_str()}] {normalized_topic.upper()} FLOW HANDLED: corruption")
            return reply_target._last_reply or "", None

        # 3) Psych / counseling (reuse shared flow)
        reply_target = MockMessage(user, "")
        reply_target._init_capture()
        handled = await handle_psych(
            update=update,
            context=context,
            reply_message=reply_target,
            raw_input=raw_input,
            normalized_input=normalized_input,
            user_id=user_id,
            username=username,
            storage_key=storage_key,
            chat_log_id=chat_log_id,
            source=normalized_topic,
            topic=normalized_topic,
            mark_responded=lambda: None,
            timeout_seconds=PSYCH_TIMEOUT_SECONDS,
            timeout_message=PSYCH_TIMEOUT_MESSAGE,
            now_ts=now_ts,
        )
        if handled:
            print(f"[{now_str()}] {normalized_topic.upper()} FLOW HANDLED: psych")
            return reply_target._last_reply or "", None

        # Teacher flow is handled via shared flow handler below

        # 4) Teacher mode (reuse shared flow)
        reply_target = MockMessage(user, "")
        reply_target._init_capture()
        handled = await handle_teacher(
            update=update,
            context=context,
            reply_message=reply_target,
            raw_input=raw_input,
            normalized_input=normalized_input,
            user_id=user_id,
            storage_key=storage_key,
            topic=normalized_topic,
            mark_responded=lambda: None,
            timeout_seconds=TEACHER_TIMEOUT_SECONDS,
            timeout_message=TEACHER_TIMEOUT_MESSAGE,
        )
        if handled:
            print(f"[{now_str()}] {normalized_topic.upper()} FLOW HANDLED: teacher")
            return reply_target._last_reply or "", None

        # 5) Smalltalk / canned (reuse shared flow)
        reply_target = MockMessage(user, "")
        reply_target._init_capture()
        handled = await handle_smalltalk(
            update=update,
            context=context,
            reply_message=reply_target,
            normalized_input=normalized_input,
            user_id=user_id,
            username=username,
            topic=normalized_topic,
            mark_responded=lambda: None,
        )
        if handled:
            print(f"[{now_str()}] {normalized_topic.upper()} FLOW HANDLED: smalltalk")
            return reply_target._last_reply or "", None

        normalized_input = rewrite_schedule_query(normalized_input)

        print(f"[{now_str()}] ASKA sedang berpikir...")

        history_from_db = get_chat_history(user_id, limit=5, offset=0)
        chat_history = format_history_for_chain(history_from_db)

        start_time = time.perf_counter()

        result = await asyncio.to_thread(qa_chain.invoke, {"input": normalized_input, "chat_history": chat_history})

        print(f"[{now_str()}] ?? ASKA AMBIL {len(result['context'])} KONTEN:")
        for i, doc in enumerate(result["context"], 1):
            print(f"  {i}. {doc.page_content[:200]}...")

        save_rag_log(
            user_id=user_id,
            username=username,
            channel=normalized_topic,
            question=normalized_input,
            chunks=[doc.page_content[:300] for doc in result["context"]],
            answer=coerce_to_text(result)[:500],
            response_ms=int((time.perf_counter() - start_time) * 1000),
        )

        response = coerce_to_text(result)
        response = remove_trailing_signature(response.strip())

        if not response:
            response = ASKA_NO_DATA_RESPONSE

        duration_ms = (time.perf_counter() - start_time) * 1000
        print(f"[{now_str()}] ASKA : {response} ?? {duration_ms:.2f} ms")
        bot_chat_log_id = save_chat(
            user_id,
            "ASKA",
            response,
            role="aska",
            topic=normalized_topic,
            response_time_ms=int(duration_ms),
        )

        return response, bot_chat_log_id

    except Exception as e:
        print(f"[{now_str()}] [ERROR] {e}")
        return ASKA_TECHNICAL_ISSUE_RESPONSE, None


async def process_web_request(user_id: int, user_input: str, username: str = "WebUser") -> tuple[str, Optional[int]]:
    """Backward-compatible wrapper for existing web endpoint."""
    return await process_channel_request(
        user_id,
        user_input,
        username=username,
        topic="web",
    )
