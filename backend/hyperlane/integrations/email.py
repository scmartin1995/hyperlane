"""Email intake: IMAP polling for new requests / replies, SMTP for the agent's clarifying questions.

- `parse_message(raw)` is pure (stdlib `email`) and unit-tested.
- `poll_inbox()` runs on the scheduler every INTAKE_POLL_SECONDS when IMAP is configured.
- `send_reply(request, body)` is called by the agent's intake flow (backend-agent) when it drafts a
  clarifying question; it is a logged no-op when SMTP is not configured.

Only the mailbox you configure is read; only replies to intake requests are ever sent.
"""

from __future__ import annotations

import asyncio
import email as _email
import html as _html
import imaplib
import inspect
import logging
import re
import smtplib
import threading
from contextlib import suppress
from datetime import datetime
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.utils import formatdate, make_msgid, parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, ClassVar

from sqlalchemy import select

from ..config import get_settings
from ..db import session_scope, utcnow
from ..models import IntakeMessage, IntakeRequest
from ..services.events import bus
from ._common import record_notification

log = logging.getLogger(__name__)

_last_poll: datetime | None = None
_last_error: str | None = None
_poll_lock = threading.Lock()


# ---------------------------------------------------------------- parsing (pure)


class _TextExtractor(HTMLParser):
    _SKIP: ClassVar[set[str]] = {"script", "style", "head", "title"}
    _BLOCK: ClassVar[set[str]] = {
        "p",
        "div",
        "br",
        "li",
        "tr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
        "pre",
    }

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def text(self) -> str:
        raw = _html.unescape("".join(self._parts))
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n\n", raw)
        return raw.strip()


def strip_html(markup: str) -> str:
    p = _TextExtractor()
    try:
        p.feed(markup)
        p.close()
    except Exception:  # noqa: BLE001 - malformed html: fall back to a tag strip
        return re.sub(r"<[^>]+>", " ", markup).strip()
    return p.text()


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except (UnicodeError, ValueError, LookupError):
        return value.strip()


def _part_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _body_of(msg: Message) -> str:
    plain: list[str] = []
    html_parts: list[str] = []
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.is_multipart():
            continue
        if (part.get_content_disposition() or "") == "attachment":
            continue
        ctype = part.get_content_type()
        if ctype == "text/plain":
            plain.append(_part_text(part))
        elif ctype == "text/html":
            html_parts.append(_part_text(part))
    if any(p.strip() for p in plain):
        return "\n".join(p for p in plain if p.strip()).strip()
    if html_parts:
        return strip_html("\n".join(html_parts))
    return ""


def _msgid_list(value: str | None) -> list[str]:
    return re.findall(r"<[^<>\s]+>", value or "")


def parse_message(raw: bytes) -> dict[str, Any]:
    """Parse a raw RFC822 message into the fields intake cares about. Pure; never raises on bad input."""
    msg = _email.message_from_bytes(raw)
    from_name, from_addr = parseaddr(_decode(msg.get("From")))
    in_reply_to = _msgid_list(msg.get("In-Reply-To"))
    references = _msgid_list(msg.get("References"))
    message_id = (_msgid_list(msg.get("Message-ID")) or [None])[0]
    date: datetime | None = None
    if msg.get("Date"):
        try:
            date = parsedate_to_datetime(msg["Date"])
        except (TypeError, ValueError):
            date = None
    return {
        "subject": _decode(msg.get("Subject")) or "(no subject)",
        "from_name": from_name.strip() or (from_addr.split("@")[0] if from_addr else ""),
        "from_addr": from_addr.strip().lower(),
        "to": _decode(msg.get("To")),
        "body": _body_of(msg),
        "message_id": message_id,
        "in_reply_to": in_reply_to[0] if in_reply_to else None,
        "references": references,
        "date": date,
    }


# ---------------------------------------------------------------- matching to intake


def find_request_for(db, parsed: dict[str, Any]) -> IntakeRequest | None:
    """A reply belongs to the request whose thread_key (or any logged message id) is referenced."""
    refs = [r for r in [parsed.get("in_reply_to"), *parsed.get("references", [])] if r]
    if not refs:
        return None
    req = db.execute(
        select(IntakeRequest).where(IntakeRequest.thread_key.in_(refs)).limit(1)
    ).scalar_one_or_none()
    if req is not None:
        return req
    im = db.execute(
        select(IntakeMessage).where(IntakeMessage.external_ref.in_(refs)).limit(1)
    ).scalar_one_or_none()
    return im.request if im is not None else None


def already_seen(db, message_id: str | None) -> bool:
    if not message_id:
        return False
    if db.execute(select(IntakeRequest.id).where(IntakeRequest.thread_key == message_id).limit(1)).first():
        return True
    return bool(
        db.execute(select(IntakeMessage.id).where(IntakeMessage.external_ref == message_id).limit(1)).first()
    )


def ingest(parsed: dict[str, Any]) -> str | None:
    """Create the IntakeRequest / IntakeMessage for a parsed mail. Returns the request id (None = skipped)."""
    request_id: str | None = None
    is_reply = False
    with session_scope() as db:
        if already_seen(db, parsed.get("message_id")):
            return None
        req = find_request_for(db, parsed)
        author = parsed.get("from_addr") or parsed.get("from_name") or "unknown"
        if req is not None:
            is_reply = True
            db.add(
                IntakeMessage(
                    request_id=req.id,
                    direction="inbound",
                    author=author,
                    body=parsed.get("body") or "",
                    external_ref=parsed.get("message_id"),
                    meta={"subject": parsed.get("subject")},
                )
            )
            req.last_activity_at = utcnow()
            if req.state in ("new", "clarifying"):
                req.state = "clarifying"
            db.flush()
            request_id = req.id
        else:
            req = IntakeRequest(
                channel="email",
                state="new",
                requester_name=parsed.get("from_name") or None,
                requester_email=parsed.get("from_addr") or None,
                subject=(parsed.get("subject") or "(no subject)")[:300],
                original_body=parsed.get("body") or "",
                thread_key=parsed.get("message_id"),
            )
            db.add(req)
            db.flush()
            db.add(
                IntakeMessage(
                    request_id=req.id,
                    direction="inbound",
                    author=author,
                    body=parsed.get("body") or "",
                    external_ref=parsed.get("message_id"),
                    meta={"subject": parsed.get("subject")},
                )
            )
            request_id = req.id
    if request_id:
        bus.emit(
            "intake.updated" if is_reply else "intake.created",
            entity_type="intake_request",
            entity_id=request_id,
            data={"channel": "email", "reply": is_reply},
        )
        _analyze(request_id)
    return request_id


def _analyze(request_id: str) -> None:
    """Hand off to the agent's intake analysis (backend-agent). Tolerates absence / failure."""
    try:
        from ..agent.intake import analyze
    except ImportError:
        log.info("agent.intake.analyze not available; request %s stays as-is", request_id)
        return
    try:
        res = analyze(request_id)
        if inspect.isawaitable(res):
            asyncio.run(res)
    except Exception:
        log.exception("intake analyze failed for %s", request_id)


# ---------------------------------------------------------------- imap polling


def _imap_connect() -> imaplib.IMAP4_SSL:
    s = get_settings()
    conn = imaplib.IMAP4_SSL(s.intake_imap_host or "", timeout=30)
    conn.login(s.intake_imap_user or "", s.intake_imap_password or "")
    return conn


def poll_inbox() -> int:
    """Fetch UNSEEN mails, ingest them, mark them seen. Returns the number ingested."""
    global _last_poll, _last_error
    s = get_settings()
    if not s.email_intake_enabled:
        log.warning("email intake not configured (INTAKE_IMAP_HOST/USER/PASSWORD); poll skipped")
        return 0
    if not _poll_lock.acquire(blocking=False):
        log.info("email poll already running; skipping")
        return 0
    count = 0
    try:
        conn = _imap_connect()
        try:
            typ, _ = conn.select(s.intake_imap_folder or "INBOX")
            if typ != "OK":
                raise RuntimeError(f"cannot select folder {s.intake_imap_folder}")
            typ, data = conn.search(None, "UNSEEN")
            ids = data[0].split() if typ == "OK" and data and data[0] else []
            for uid in ids:
                try:
                    typ, fetched = conn.fetch(uid, "(BODY.PEEK[])")
                    raw = next((p[1] for p in fetched if isinstance(p, tuple)), None)
                    if typ != "OK" or raw is None:
                        continue
                    parsed = parse_message(raw)
                    if ingest(parsed):
                        count += 1
                    conn.store(uid, "+FLAGS", "\\Seen")
                except Exception:
                    log.exception("failed to ingest mail %s", uid)
        finally:
            with suppress(Exception):
                conn.logout()
        _last_error = None
    except Exception as e:  # noqa: BLE001 - network/API errors are logged + recorded, never raised
        _last_error = str(e)
        log.error("email poll failed: %s", e)
    finally:
        _last_poll = utcnow()
        _poll_lock.release()
    if count:
        log.info("email intake: %d new message(s)", count)
    return count


# ---------------------------------------------------------------- smtp replies


def _smtp_configured() -> bool:
    s = get_settings()
    return bool(s.intake_smtp_host and s.intake_from_address)


def send_reply(request: IntakeRequest, body: str, subject: str | None = None) -> str | None:
    """Email `body` to the requester, threaded on the request. Returns the new Message-ID or None."""
    s = get_settings()
    to_addr = request.requester_email
    if not _smtp_configured():
        log.warning("email reply not sent: SMTP not configured (INTAKE_SMTP_HOST + INTAKE_FROM_ADDRESS)")
        return None
    if not to_addr:
        log.warning("email reply not sent: request %s has no requester email", request.id)
        return None
    subj = subject or request.subject or "Your request"
    if not subj.lower().startswith("re:"):
        subj = f"Re: {subj}"
    msg = EmailMessage()
    msg["From"] = s.intake_from_address
    msg["To"] = to_addr
    msg["Subject"] = subj
    msg["Date"] = formatdate(localtime=True)
    domain = (s.intake_from_address or "hyperlane.local").split("@")[-1]
    msg_id = make_msgid(domain=domain)
    msg["Message-ID"] = msg_id
    if request.thread_key:
        msg["In-Reply-To"] = request.thread_key
        msg["References"] = request.thread_key
    msg.set_content(body)
    err: str | None = None
    try:
        with smtplib.SMTP(s.intake_smtp_host or "", s.intake_smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            try:
                smtp.starttls()
                smtp.ehlo()
            except smtplib.SMTPNotSupportedError:
                log.warning("SMTP server does not support STARTTLS; continuing unencrypted")
            if s.intake_smtp_user and s.intake_smtp_password:
                smtp.login(s.intake_smtp_user, s.intake_smtp_password)
            smtp.send_message(msg)
    except Exception as e:  # noqa: BLE001 - network/API errors are logged + recorded, never raised
        err = str(e)
        log.error("email reply failed to %s: %s", to_addr, err)
    record_notification(
        channel="email",
        target=to_addr,
        kind="intake_reply",
        body=body,
        ok=err is None,
        error=err,
        external_ref=msg_id[:120] if err is None else None,
        entity_type="intake_request",
        entity_id=request.id,
        project_id=request.project_id,
        meta={"subject": subj},
    )
    if err:
        return None
    try:
        with session_scope() as db:
            db.add(
                IntakeMessage(
                    request_id=request.id,
                    direction="outbound",
                    author=s.intake_from_address or "Hyperlane",
                    body=body,
                    external_ref=msg_id,
                    meta={"subject": subj, "sent": True},
                )
            )
    except Exception:  # pragma: no cover
        log.exception("could not log outbound intake message")
    return msg_id


# ---------------------------------------------------------------- status / test


def test_connection() -> dict[str, Any]:
    s = get_settings()
    if not s.email_intake_enabled:
        return {"ok": False, "detail": "IMAP not configured (INTAKE_IMAP_HOST / USER / PASSWORD)"}
    try:
        conn = _imap_connect()
        try:
            typ, data = conn.select(s.intake_imap_folder or "INBOX", readonly=True)
            n = data[0].decode() if typ == "OK" and data and data[0] else "?"
        finally:
            conn.logout()
    except Exception as e:  # noqa: BLE001 - network/API errors are logged + recorded, never raised
        return {"ok": False, "detail": f"IMAP login failed: {e}"}
    detail = f"IMAP login ok; {n} message(s) in {s.intake_imap_folder}"
    detail += "; SMTP configured" if _smtp_configured() else "; SMTP not configured (replies disabled)"
    return {"ok": True, "detail": detail}


def status() -> dict[str, Any]:
    s = get_settings()
    if not s.email_intake_enabled:
        detail = "not configured (INTAKE_IMAP_HOST / USER / PASSWORD)"
    elif _last_error:
        detail = f"last poll failed: {_last_error}"
    else:
        detail = f"polling {s.intake_imap_folder} every {s.intake_poll_seconds}s"
        detail += "; replies on" if _smtp_configured() else "; replies off (no SMTP)"
    return {
        "enabled": s.email_intake_enabled,
        "detail": detail,
        "last_poll": _last_poll.isoformat() if _last_poll else None,
    }
