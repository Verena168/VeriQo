"""Check the Gmail SMTP settings in backend/.env by sending one email directly (not via the outbox).

    python scripts/send_test_email.py you@example.com

Gmail needs: 2-Step Verification on the account, then an App Password from
https://myaccount.google.com/apppasswords. Put the Gmail address in SMTP_USER and the 16-character
App Password in SMTP_PASSWORD. The normal account password will be rejected (error 535).
"""

import smtplib
import sys

from app.core.config import get_settings
from app.services.email import build_message, render, send_blocking, smtp_configured


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/send_test_email.py recipient@example.com")
    s = get_settings()
    if not smtp_configured():
        sys.exit("SMTP_USER and SMTP_PASSWORD are not set in backend/.env")
    print(f"Sending via {s.smtp_host}:{s.smtp_port} as {s.smtp_user} ...")
    try:
        send_blocking(build_message(sys.argv[1], render("test", {})))
    except smtplib.SMTPAuthenticationError:
        sys.exit("Login rejected (535). Use a Gmail App Password, not your normal password, and check SMTP_USER.")
    except (smtplib.SMTPException, OSError) as exc:
        sys.exit(f"Sending failed: {type(exc).__name__}: {exc}")
    print("Sent. Check the inbox (and the spam folder).")


if __name__ == "__main__":
    main()
