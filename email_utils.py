import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

def send_recovery_email(target_email, recovery_code):
    """Sends a real email containing the 6-digit recovery code."""
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")

    if not sender_email or not sender_password:
        return False, "Email credentials missing in .env file."

    subject = "StaffScore: Your Password Recovery Code"
    body = f"""Hello,

We received a request to reset your StaffScore password. 
Your 6-digit recovery code is: {recovery_code}

If you did not request this, please ignore this email.

Best regards,
StaffScore IT Team"""

    msg = MIMEMultipart()
    msg['From'] = f"StaffScore IT <{sender_email}>"
    msg['To'] = target_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        # Connect to Gmail's secure SMTP server
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        return True, "Email sent successfully!"
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"