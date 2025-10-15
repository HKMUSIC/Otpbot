import imaplib
import email
from bs4 import BeautifulSoup
import re

EMAIL = "drxsupport@animetoons.site"
PASSWORD = "Stalker@123"
IMAP_SERVER = "mail.animetoons.site"
IMAP_PORT = 993
FAMPAY_SENDER = "no-reply@famapp.in"  # Fampay official sender email

def check_fampay_emails(txn_id_to_check):
    """
    Connects to Fampay inbox and checks if a transaction ID exists.
    Returns (found: bool, sender: str)
    """
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL, PASSWORD)
        mail.select("INBOX")

        # Fetch only unseen emails from Fampay
        status, data = mail.search(None, f'(FROM "{FAMPAY_SENDER}" UNSEEN)')
        email_ids = data[0].split()

        for num in email_ids:
            status, msg_data = mail.fetch(num, "(RFC822)")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode()
                        break
                    elif part.get_content_type() == "text/html":
                        html_body = part.get_payload(decode=True).decode()
                        body = BeautifulSoup(html_body, "html.parser").get_text()
                        break
            else:
                body = msg.get_payload(decode=True).decode()

            body = body.replace("\n", " ").replace("\r", "")

            txn_match = re.search(r"transaction id (\w+)", body, re.IGNORECASE)
            sender_match = re.search(r"from ([A-Za-z ]+) at", body)

            if txn_match and txn_match.group(1) == txn_id_to_check:
                sender = sender_match.group(1) if sender_match else "Unknown"
                return True, sender

        mail.logout()
    except Exception as e:
        print("❌ IMAP check failed:", e)

    return False, ""
