import os
from supabase import create_client, Client
from datetime import datetime
from dotenv import load_dotenv
import json

load_dotenv()

# Initialize Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in .env file")

SUPABASE_URL = SUPABASE_URL.strip().strip('"').strip("'")
SUPABASE_KEY = SUPABASE_KEY.strip().strip('"').strip("'")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Error creating Supabase client: {e}")
    raise

# ==========================================
# AUTH OPERATIONS
# ==========================================

def sign_up_user(email, password):
    """Register a new user"""
    try:
        response = supabase.auth.sign_up({
            "email": email, 
            "password": password
        })
        return response.user
    except Exception as e:
        print(f"Sign up error: {e}")
        return None

def sign_in_user(email, password):
    """Login existing user"""
    try:
        response = supabase.auth.sign_in_with_password({
            "email": email, 
            "password": password
        })
        return response.user
    except Exception as e:
        print(f"Sign in error: {e}")
        return None

def sign_out_user():
    """Logout user"""
    try:
        supabase.auth.sign_out()
    except Exception as e:
        print(f"Sign out error: {e}")

# ==========================================
# ASSET OPERATIONS
# ==========================================

def save_asset(asset_data, user_id):
    """Save or update an asset for a specific user."""
    try:
        # Check if asset exists for THIS user
        existing = supabase.table('assets')\
            .select('*')\
            .eq('name', asset_data['name'])\
            .eq('user_id', user_id)\
            .execute()
        
        payload = {
            'user_id': user_id,
            'name': asset_data['name'],
            'type': asset_data['type'],
            'lat': asset_data['lat'],
            'lon': asset_data['lon'],
            'importance': asset_data['importance'],
            'radius': asset_data['radius'],
            'updated_at': datetime.utcnow().isoformat()
        }

        if existing.data:
            result = supabase.table('assets').update(payload).eq('id', existing.data[0]['id']).execute()
            return result.data[0]
        else:
            payload['created_at'] = datetime.utcnow().isoformat()
            result = supabase.table('assets').insert(payload).execute()
            return result.data[0]
    except Exception as e:
        print(f"Error saving asset: {e}")
        return None

def get_user_assets(user_id):
    """
    APP USE ONLY: Retrieve assets belonging to the logged-in user.
    """
    try:
        result = supabase.table('assets')\
            .select('*')\
            .eq('user_id', user_id)\
            .order('created_at')\
            .execute()
        return result.data
    except Exception as e:
        print(f"Error fetching assets: {e}")
        return []

def get_all_assets():
    """
    MONITOR USE ONLY: Retrieve ALL assets system-wide.
    Used by the headless monitor.py script.
    """
    try:
        result = supabase.table('assets').select('*').order('created_at').execute()
        return result.data
    except Exception as e:
        print(f"Error fetching all assets: {e}")
        return []

def delete_asset(asset_id):
    """Delete an asset by ID."""
    try:
        supabase.table('assets').delete().eq('id', asset_id).execute()
        return True
    except Exception as e:
        print(f"Error deleting asset: {e}")
        return False

def bulk_save_assets(assets_list, user_id):
    """Save multiple assets at once for a user."""
    saved_assets = []
    for asset in assets_list:
        result = save_asset(asset, user_id)
        if result:
            saved_assets.append(result)
    return saved_assets

# ==========================================
# ANALYSIS OPERATIONS
# ==========================================

def save_analysis(asset_id, risk_topic, weather_data, articles, max_risk_score):
    """Save an analysis run."""
    try:
        result = supabase.table('analyses').insert({
            'asset_id': asset_id,
            'risk_topic': risk_topic,
            'weather_data': json.dumps(weather_data),
            'max_risk_score': max_risk_score,
            'analyzed_at': datetime.utcnow().isoformat()
        }).execute()
        
        analysis_id = result.data[0]['id']
        for article in articles:
            save_threat(analysis_id, article)
        return result.data[0]
    except Exception as e:
        print(f"Error saving analysis: {e}")
        return None

def get_latest_analysis(asset_id, limit=1):
    """Get the most recent analysis for an asset."""
    try:
        result = supabase.table('analyses')\
            .select('*')\
            .eq('asset_id', asset_id)\
            .order('analyzed_at', desc=True)\
            .limit(limit)\
            .execute()
        
        if limit == 1: return result.data[0] if result.data else None
        return result.data
    except Exception as e:
        return None

# ==========================================
# THREAT OPERATIONS
# ==========================================

def save_threat(analysis_id, threat_data):
    """Save a threat associated with an analysis."""
    try:
        supabase.table('threats').insert({
            'analysis_id': analysis_id,
            'headline': threat_data.get('Headline'),
            'source': threat_data.get('Source'),
            'published_date': threat_data.get('Published'),
            'url': threat_data.get('URL'),
            'risk_score': threat_data.get('risk_score', 0),
            'severity': threat_data.get('severity'),
            'reasoning': threat_data.get('reasoning'),
            'action': threat_data.get('action'),
            'impacted_asset': threat_data.get('impacted_asset')
        }).execute()
    except Exception as e:
        print(f"Error saving threat: {e}")

def get_threats_for_analysis(analysis_id):
    """Get all threats for a specific analysis."""
    try:
        result = supabase.table('threats').select('*').eq('analysis_id', analysis_id).order('risk_score', desc=True).execute()
        return result.data
    except Exception: return []

# ==========================================
# ALERT OPERATIONS
# ==========================================

def save_alert(threat_id, alert_type, recipient, status='sent'):
    """Log an alert that was sent."""
    try:
        result = supabase.table('alerts').insert({
            'threat_id': threat_id,
            'alert_type': alert_type,
            'recipient': recipient,
            'status': status,
            'sent_at': datetime.utcnow().isoformat()
        }).execute()
        
        return result.data[0]
    except Exception as e:
        print(f"Error saving alert: {e}")
        return None

def get_recent_alerts(hours=24):
    """Get alerts sent in the last N hours."""
    try:
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        
        result = supabase.table('alerts')\
            .select('*')\
            .gte('sent_at', cutoff)\
            .order('sent_at', desc=True)\
            .execute()
        
        return result.data
    except Exception as e:
        print(f"Error fetching recent alerts: {e}")
        return []

# ==========================================
# UTILITY FUNCTIONS
# ==========================================

def get_dashboard_stats(user_id=None):
    """Get stats."""
    try:
        assets = get_user_assets(user_id) if user_id else []
        return {
            'total_assets': len(assets),
            'analyses_24h': 0,
            'critical_threats': 0,
            'avg_risk_score': 0
        }
    except Exception as e:
        return {}