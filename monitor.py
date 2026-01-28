import os  # <--- THIS WAS MISSING
import time
import schedule
import sys
from datetime import datetime
from dotenv import load_dotenv

# Import your existing modules
from database import get_all_assets, save_analysis, save_alert
from ingestion import fetch_weather_coords, fetch_news, parse_weather_risk, parse_news_risk, reverse_geocode
from risk_engine import assess_news_risk
from notifications import send_email_alert

# --- TEST CONFIGURATION ---
RISK_THRESHOLD = 0  # <--- SET TO 0 FOR TESTING (Normally 75)
CHECK_INTERVAL_MINUTES = 60
ALERT_RECIPIENT = "YOUR_EMAIL_HERE" # Fallback if not in .env

def run_sentinel_scan():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🛰️ Starting Sentinel Scan...")
    
    # 1. Fetch Assets
    assets = get_all_assets()
    if not assets:
        print("   ⚠️ No assets found in database. Please run app.py and add assets first.")
        return

    print(f"   📋 Monitoring {len(assets)} assets.")

    for asset in assets:
        try:
            # Skip unconfigured assets
            if not asset.get('lat'): 
                continue
            
            print(f"   🔍 Scanning: {asset['name']}...")
            
            # 2. Fetch Data
            w_raw = fetch_weather_coords(asset['lat'], asset['lon'])
            w_clean = parse_weather_risk(w_raw)
            
            city = reverse_geocode(asset['lat'], asset['lon'])
            if not city:
                city = asset['name'] # Fallback
            
            # Fetch News
            news_raw = fetch_news("logistics supply chain", location=city)
            articles = parse_news_risk(news_raw)
            
            # 3. AI Analysis
            enhanced_articles = []
            max_risk = 0
            critical_threat = None
            
            if articles:
                print(f"      -> Found {len(articles)} articles. Analyzing Top 3...")
                for art in articles[:3]: # Limit to 3 for speed
                    ai_input = {"headline": art["Headline"], "summary": art.get("summary", art["Headline"])}
                    
                    # Call AI
                    assessment = assess_news_risk(ai_input, weather_data=w_clean)
                    art.update(assessment)
                    enhanced_articles.append(art)
                    
                    if assessment['risk_score'] > max_risk:
                        max_risk = assessment['risk_score']
                        critical_threat = art
            else:
                print("      -> No news articles found.")

            # 4. Save to DB
            if asset.get('id'):
                save_analysis(
                    asset_id=asset['id'],
                    risk_topic="Automated Monitor",
                    weather_data=w_clean,
                    articles=enhanced_articles,
                    max_risk_score=max_risk
                )
            
            # 5. ALERT LOGIC
            print(f"      -> Max Risk Score: {max_risk}/100 (Threshold: {RISK_THRESHOLD})")
            
            if max_risk > RISK_THRESHOLD and critical_threat:
                print(f"   🚨 TRIGGERING ALERT...")
                
                risk_payload = {
                    "asset_name": asset['name'],
                    "score": max_risk,
                    "location": f"{city} (Temp: {w_clean.get('temp_c')}C)",
                    "summary": critical_threat.get('reasoning', 'No summary.'),
                    "action": critical_threat.get('action', 'Check dashboard.')
                }
                
                # Send Email
                sent = send_email_alert(ALERT_RECIPIENT, risk_payload)
                
                if sent:
                    print("      ✅ Email Sent Successfully!")
                    # Log to DB
                    save_alert(
                        threat_id=None,
                        alert_type="email",
                        recipient=ALERT_RECIPIENT,
                        status="sent"
                    )
                else:
                    print("      ❌ Email Failed to Send.")
            else:
                print(f"   ✅ No alerts triggered.")
                
        except Exception as e:
            print(f"   ❌ Error scanning {asset.get('name')}: {e}")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 💤 Scan Complete.")

if __name__ == "__main__":
    load_dotenv()
    
    # Try to get recipient from env, otherwise keep the default at top
    env_recipient = os.getenv("ALERT_RECIPIENT")
    if env_recipient:
        ALERT_RECIPIENT = env_recipient
        
    print(f"🛡️ Sentinel Monitor Online")
    print(f"   Target Email: {ALERT_RECIPIENT}")
    
    if "YOUR_EMAIL" in ALERT_RECIPIENT:
        print("❌ ERROR: Please set ALERT_RECIPIENT in .env or at top of monitor.py")
        sys.exit()

    # Run once immediately
    run_sentinel_scan()
    
    # Schedule
    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(run_sentinel_scan)
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Monitor Stopped.")
            break