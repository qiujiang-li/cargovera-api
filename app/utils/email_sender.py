import os
from email.message import EmailMessage
from app.core.config import settings
import aiosmtplib

async def send_email_async(to_email: str, cc_email: str, subject: str, body: str, subtype: str = "html"):
    message = EmailMessage()
    message["From"] = os.getenv("EMAIL_FROM", "noreply@cargovera.com")
    message["To"] = to_email
    message["Cc"] = cc_email
    message["Subject"] = subject
    message.set_content(body, subtype=subtype)

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=int(settings.smtp_port),
        username=settings.smtp_username,
        password=settings.smtp_password,
        use_tls=True
    )