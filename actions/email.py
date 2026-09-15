"""
Email — read and send emails via SMTP/IMAP.

Stores credentials in config/api_keys.json under the 'email' key namespace.
Works with any standard SMTP/IMAP server (Gmail, Outlook, iCloud, custom).
No Google API OAuth required — pure SMTP/IMAP.
"""
from __future__ import annotations

import json
import smtplib
import ssl
import sys
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from imaplib import IMAP4_SSL
from pathlib import Path
from typing import Optional


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


CONFIG_PATH = _base_dir() / "config" / "api_keys.json"


# ── Config loading ─────────────────────────────────────────────────────────────

def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_email_config() -> dict:
    """Return the 'email' config block, or None if not configured."""
    cfg = _load_config()
    return cfg.get("email")


def _require_email_config() -> dict:
    cfg = _get_email_config()
    if not cfg or not cfg.get("email_address"):
        raise RuntimeError(
            "Email not configured. Add an 'email' block to config/api_keys.json "
            "with: email_address, password, smtp_server, smtp_port, imap_server, imap_port."
        )
    return cfg


# ── Send ───────────────────────────────────────────────────────────────────────

def send_email(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    Send an email via SMTP.

    Parameters:
        to        : recipient address (string or comma-separated list)
        subject   : email subject line
        body      : email body (plain text)
        html      : optional HTML body
        cc        : optional CC addresses (comma-separated)
        bcc       : optional BCC addresses (comma-separated)
        attachment: optional file path to attach
    """
    params    = parameters or {}
    try:
        cfg       = _require_email_config()
    except RuntimeError as e:
        return str(e)

    addr      = cfg["email_address"]
    password  = cfg.get("password", "")
    smtp_srv  = cfg.get("smtp_server", "smtp.gmail.com")
    smtp_port = int(cfg.get("smtp_port", 587))

    to_addrs     = [a.strip() for a in (params.get("to", "")).split(",") if a.strip()]
    subject      = (params.get("subject") or "").strip()
    body         = (params.get("body") or params.get("message") or "").strip()
    html_body    = (params.get("html") or "").strip()
    cc_addrs     = [a.strip() for a in (params.get("cc") or "").split(",") if a.strip()]
    bcc_addrs    = [a.strip() for a in (params.get("bcc") or "").split(",") if a.strip()]
    attachment   = (params.get("attachment") or "").strip()

    if not to_addrs:
        return "Please specify at least one recipient ('to')."
    if not body and not html_body:
        return "Please provide an email body or HTML content."

    msg = MIMEMultipart("alternative" if html_body else "mixed")
    msg["From"]    = addr
    msg["To"]      = ", ".join(to_addrs)
    msg["Subject"] = subject or "(no subject)"
    if cc_addrs:
        msg["Cc"] = ", ".join(cc_addrs)

    # Attach plain-text body
    if body:
        msg.attach(MIMEText(body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Attach file if requested
    if attachment:
        att_path = Path(attachment)
        if att_path.exists():
            from email.mime.base import MIMEBase
            import mimetypes
            ctype, _ = mimetypes.guess_type(str(att_path))
            if ctype is None:
                ctype = "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)
            with open(att_path, "rb") as f:
                part = MIMEBase(maintype, subtype)
                part.set_payload(f.read())
            part.add_header("Content-Disposition", f"attachment; filename={att_path.name}")
            msg.attach(part)
        else:
            print(f"[Email] ⚠️ Attachment not found: {attachment}")

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_srv, smtp_port, timeout=30) as server:
            server.starttls(context=context)
            server.login(addr, password)
            final_recipients = to_addrs + cc_addrs + bcc_addrs
            server.sendmail(addr, final_recipients, msg.as_string())
        if player:
            player.write_log(f"[Email] ✅ Sent to {', '.join(to_addrs)}")
        return f"Email sent to {', '.join(to_addrs)}"
    except Exception as e:
        err_msg = str(e)
        print(f"[Email] ❌ Send failed: {err_msg}")
        if player:
            player.write_log(f"[Email] ❌ Send failed: {err_msg[:80]}")
        return f"Could not send email: {err_msg}"


# ── Read ───────────────────────────────────────────────────────────────────────

def read_emails(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    Read recent emails from the inbox.

    Parameters:
        limit     : number of recent emails to fetch (default: 10)
        folder    : IMAP folder to read from (default: 'INBOX')
        unread_only: if True, only fetch unread emails
        keyword   : optional subject/body keyword filter
    """
    try:
        params      = parameters or {}
        cfg         = _require_email_config()
        addr        = cfg["email_address"]
        password    = cfg.get("password", "")
        imap_srv    = cfg.get("imap_server", "imap.gmail.com")
        imap_port   = int(cfg.get("imap_port", 993))
        limit       = min(int(params.get("limit") or 10), 50)
        folder      = (params.get("folder") or "INBOX").upper()
        unread_only = bool(params.get("unread_only", False))
        keyword     = (params.get("keyword") or "").strip().lower()
    except RuntimeError as e:
        return str(e)

    try:
        mail = IMAP4_SSL(imap_srv, imap_port)
        mail.login(addr, password)
        mail.select(folder)

        # Build search criteria
        if unread_only:
            search_criteria = b"UNSEEN"
        else:
            search_criteria = b"ALL"

        status, response = mail.search(None, search_criteria)
        if status != "OK":
            return "Could not read inbox."

        msg_ids = response[0].split()
        if not msg_ids:
            mail.logout()
            return "No emails found."

        # Get the most recent `limit` messages
        recent_ids = msg_ids[-limit:]
        recent_ids.reverse()  # newest first

        results = []
        for msg_id in recent_ids:
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
            email_msg = _parse_raw_email(raw)

            if keyword and keyword not in (
                email_msg.get("subject", "") + email_msg.get("from", "") + email_msg.get("body", "")
            ).lower():
                continue

            results.append(email_msg)

        mail.logout()

        if not results:
            return "No emails found matching your criteria."

        lines = [f"Recent emails in {folder} ({len(results)} shown):", ""]
        for i, em in enumerate(results, 1):
            preview = em.get("body", "")[:120].replace("\n", " ")
            lines.append(
                f"{i}. [{em.get('date', '?')}] {em.get('from', '?')}: {em.get('subject', '(no subject)')}"
            )
            if preview:
                lines.append(f"   {preview}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        err_msg = str(e)
        print(f"[Email] ❌ Read failed: {err_msg}")
        if player:
            player.write_log(f"[Email] ❌ Read failed: {err_msg[:80]}")
        return f"Could not read emails: {err_msg}"


def _parse_raw_email(raw: bytes) -> dict:
    """Parse raw MIME bytes into a structured dict."""
    import email
    msg = email.message_from_bytes(raw)

    # Decode headers
    def _decode_header(h):
        if not h:
            return ""
        parts = email.header.decode_header(h)
        result = []
        for part, charset in parts:
            if isinstance(part, bytes):
                result.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                result.append(part)
        return " ".join(result)

    date_str = _decode_header(msg.get("Date", ""))
    from_str = _decode_header(msg.get("From", ""))
    subj     = _decode_header(msg.get("Subject", ""))

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                try:
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                    break
                except Exception:
                    continue
    else:
        try:
            body = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace"
            )
        except Exception:
            pass

    return {
        "date":    date_str,
        "from":    from_str,
        "subject": subj,
        "body":    body.strip()[:500],
    }


# ── Configure ──────────────────────────────────────────────────────────────────

def configure_email(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    Save email credentials to config/api_keys.json.

    Parameters:
        email_address : sender email address
        password      : app password or SMTP password
        smtp_server   : SMTP server (default: smtp.gmail.com)
        smtp_port     : SMTP port (default: 587)
        imap_server   : IMAP server (default: imap.gmail.com)
        imap_port     : IMAP port (default: 993)
    """
    params   = parameters or {}
    cfg      = _load_config()

    email_cfg: dict = {
        "email_address": (params.get("email_address") or "").strip(),
        "password":      (params.get("password") or "").strip(),
        "smtp_server":   params.get("smtp_server") or "smtp.gmail.com",
        "smtp_port":     int(params.get("smtp_port") or 587),
        "imap_server":   params.get("imap_server") or "imap.gmail.com",
        "imap_port":     int(params.get("imap_port") or 993),
    }

    if not email_cfg["email_address"]:
        return "Please provide an email address."

    cfg["email"] = email_cfg
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    if player:
        player.write_log("[Email] Configuration saved.")
    return f"Email configured for {email_cfg['email_address']}. You can now send and read emails."


# ── Unified entry point ────────────────────────────────────────────────────────

def email(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    Unified entry point for email operations.
    Gemini should set the `action` parameter to route to the right handler.
    """
    params    = parameters or {}
    action    = (params.get("action") or "read").lower().strip()

    if action in ("send", "compose", "write"):
        return send_email(params, player, session_memory)
    if action in ("read", "inbox", "check"):
        return read_emails(params, player, session_memory)
    if action in ("configure", "setup", "login"):
        return configure_email(params, player, session_memory)
    return (
        f"Unknown email action: '{action}'. "
        "Use 'send' to send an email, 'read' to check inbox, or 'configure' to set up credentials."
    )


# ── Tool declaration ───────────────────────────────────────────────────────────

TOOL = {
    "name": "email",
    "description": (
        "Read and send emails. Use 'action=read' to check your inbox "
        "(recent unread or all emails), 'action=send' to send an email "
        "(requires prior configuration), or 'action=configure' to set up "
        "your SMTP/IMAP credentials on first use. Works with Gmail, "
        "Outlook, iCloud, and any standard email provider. Credentials "
        "are stored locally in config/api_keys.json."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "send | read | configure",
            },
            # Send params
            "to": {
                "type": "STRING",
                "description": "Recipient email address (comma-separated for multiple).",
            },
            "subject": {
                "type": "STRING",
                "description": "Email subject line.",
            },
            "body": {
                "type": "STRING",
                "description": "Email body text.",
            },
            "html": {
                "type": "STRING",
                "description": "Optional HTML body.",
            },
            "cc": {
                "type": "STRING",
                "description": "Optional CC addresses.",
            },
            "bcc": {
                "type": "STRING",
                "description": "Optional BCC addresses.",
            },
            "attachment": {
                "type": "STRING",
                "description": "Optional file path to attach.",
            },
            # Read params
            "limit": {
                "type": "INTEGER",
                "description": "Number of recent emails to fetch (default: 10, max: 50).",
            },
            "folder": {
                "type": "STRING",
                "description": "IMAP folder to read from (default: INBOX).",
            },
            "unread_only": {
                "type": "BOOLEAN",
                "description": "Only fetch unread emails.",
            },
            "keyword": {
                "type": "STRING",
                "description": "Optional keyword filter on subject/body/from.",
            },
            # Configure params
            "email_address": {
                "type": "STRING",
                "description": "Your email address.",
            },
            "password": {
                "type": "STRING",
                "description": "Your email password or app-specific password.",
            },
            "smtp_server": {
                "type": "STRING",
                "description": "SMTP server (default: smtp.gmail.com).",
            },
            "smtp_port": {
                "type": "INTEGER",
                "description": "SMTP port (default: 587).",
            },
            "imap_server": {
                "type": "STRING",
                "description": "IMAP server (default: imap.gmail.com).",
            },
            "imap_port": {
                "type": "INTEGER",
                "description": "IMAP port (default: 993).",
            },
        },
        "required": ["action"],
    },
    "handler": email,
}
