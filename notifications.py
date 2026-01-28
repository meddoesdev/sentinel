import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

# CONFIGURATION
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
# Make sure these are in your .env file
SENDER_EMAIL = os.getenv("EMAIL_USER")
SENDER_PASSWORD = os.getenv("EMAIL_PASS")

def send_email_alert(recipient_email, risk_data):
    """
    Sends a styled HTML email alert.
    risk_data dict must contain: asset_name, score, location, summary, action
    """
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("⚠️ Email credentials missing. Skipping notification.")
        return False

    try:
        # 1. Create Email Content
        subject = f"🚨 CRITICAL ALERT: {risk_data['asset_name']} (Risk: {risk_data['score']})"
        
        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <div style="background-color: #d32f2f; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0;">
                    <h1 style="margin:0;">CRITICAL THREAT DETECTED</h1>
                    <p style="margin:5px 0; font-size: 18px;">Action Required Immediately</p>
                </div>
                
                <div style="border: 1px solid #ddd; padding: 20px; border-top: none;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 10px; font-weight: bold;">Target Asset:</td>
                            <td style="padding: 10px;">{risk_data['asset_name']}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; font-weight: bold;">Risk Score:</td>
                            <td style="padding: 10px; color: #d32f2f; font-weight: bold;">{risk_data['score']}/100</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; font-weight: bold;">Location:</td>
                            <td style="padding: 10px;">{risk_data['location']}</td>
                        </tr>
                    </table>
                    
                    <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                    
                    <h3 style="color: #444;">🤖 Intelligence Summary</h3>
                    <p style="background-color: #f9f9f9; padding: 15px; border-left: 4px solid #d32f2f;">
                        {risk_data['summary']}
                    </p>
                    
                    <h3 style="color: #444;">🛡️ Recommended Action</h3>
                    <div style="background-color: #ffebee; color: #b71c1c; padding: 15px; border-radius: 4px; font-family: monospace;">
                        {risk_data['action']}
                    </div>
                    
                    <br>
                    <center>
                        <a href="http://10.215.199.71:8501" style="background-color: #333; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">Open Sentinel Dashboard</a>                    </center>
                </div>
            </body>
        </html>
        """

        # 2. Setup Message
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(html_body, 'html'))

        # 3. Connect & Send
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        server.quit()
        
        print(f"✅ Alert sent to {recipient_email}")
        return True

    except Exception as e:
        print(f"❌ Failed to send email: {str(e)}")
        return False