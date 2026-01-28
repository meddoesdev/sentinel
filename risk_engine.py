import os
import math
import instructor
from openai import OpenAI
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# 1. SETUP OPENAI CLIENT
client = instructor.patch(OpenAI(api_key=os.getenv("OPENAI_API_KEY")))

# 2. THE ASSET REGISTRY (Dynamic - can be updated)
# In a real app, this would come from a database (PostgreSQL).
# 'importance': 1 (Low) to 10 (Critical HQ). 
# 'radius': How close an event must be to matter (in km).
ASSET_REGISTRY = [
    {
        "id": "MUM-WH-01",
        "name": "Mumbai Central Warehouse",
        "type": "Logistics Hub",
        "lat": 19.0760, 
        "lon": 72.8777,
        "importance": 8, 
        "radius": 10
    },
    {
        "id": "DEL-HU-05",
        "name": "Delhi Distribution Center",
        "type": "Distribution",
        "lat": 28.7041, 
        "lon": 77.1025,
        "importance": 5, 
        "radius": 15
    },
    {
        "id": "BLR-HQ-99",
        "name": "Bengaluru Global HQ",
        "type": "Headquarters",
        "lat": 12.9716, 
        "lon": 77.5946,
        "importance": 10, 
        "radius": 5
    },
    {
        "id": "CHE-PT-02",
        "name": "Chennai Port Operations",
        "type": "Port Access",
        "lat": 13.0827, 
        "lon": 80.2707,
        "importance": 9, 
        "radius": 20
    }
]

def update_asset_registry(assets_list):
    """
    Updates the global ASSET_REGISTRY with user-provided assets.
    This function will be replaced with database calls in production.
    
    Args:
        assets_list: List of dictionaries with keys: name, type, lat, lon, importance, radius
    """
    global ASSET_REGISTRY
    ASSET_REGISTRY = []
    
    for idx, asset in enumerate(assets_list):
        ASSET_REGISTRY.append({
            "id": f"ASSET-{idx+1:03d}",
            "name": asset['name'],
            "type": asset['type'],
            "lat": asset['lat'],
            "lon": asset['lon'],
            "importance": asset['importance'],
            "radius": asset['radius']
        })

# 3. OUTPUT SCHEMA
class RiskAssessment(BaseModel):
    risk_score: int = Field(..., description="0-100 score. 0=Safe, 100=Critical.")
    severity: str = Field(..., description="LOW, MEDIUM, HIGH, CRITICAL")
    reasoning: str = Field(..., description="Why this is a risk to the specific asset.")
    action: str = Field(..., description="Operational recommendation (e.g., 'Activate backup generators').")
    estimated_impact_radius: int = Field(..., description="Estimated radius of the event in km (e.g. 5 for a fire, 100 for a storm).")

# 4. MATH ENGINE: HAVERSINE FORMULA
def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculates the great-circle distance between two points on the Earth surface.
    Returns distance in Kilometers.
    """
    R = 6371  # Earth radius in km
    
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    
    a = (math.sin(d_lat / 2) * math.sin(d_lat / 2) +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(d_lon / 2) * math.sin(d_lon / 2))
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_impacted_assets(event_lat, event_lon):
    """
    PROXIMITY TRIGGER LOGIC:
    Filters the Asset Registry to find any asset where:
    Distance(Event, Asset) < Asset.radius
    """
    impacted = []
    
    for asset in ASSET_REGISTRY:
        distance = calculate_distance(event_lat, event_lon, asset['lat'], asset['lon'])
        
        # Logic: If the event is within the asset's "Concern Zone"
        if distance <= asset['radius']:
            asset_copy = asset.copy()
            asset_copy['distance_from_event_km'] = round(distance, 2)
            impacted.append(asset_copy)
            
    # Sort by Importance Score (Highest first) so we protect critical assets first
    impacted.sort(key=lambda x: x['importance'], reverse=True)
    return impacted

# 5. MAIN ASSESSMENT FUNCTION
def assess_news_risk(article_input, weather_data=None):
    """
    1. Checks Proximity (Math).
    2. Checks Context (LLM).
    3. Merges them into a Risk Score.
    """
    
    # A. Extract Coordinates of the SEARCH TARGET (The "Event" Center)
    # Default to 0,0 if missing, but typically weather_data provides the search center
    event_lat = weather_data.get('lat', 0)
    event_lon = weather_data.get('lon', 0)
    
    # B. Run Proximity Trigger
    nearby_assets = get_impacted_assets(event_lat, event_lon)
    
    # If NO assets are nearby, we still run analysis but flag it as "General"
    if not nearby_assets:
        primary_asset_context = "General Supply Chain (No specific asset in range)"
        importance_multiplier = 1.0
    else:
        # Take the most important asset found
        target = nearby_assets[0]
        primary_asset_context = f"{target['name']} ({target['type']}) - {target['distance_from_event_km']}km away"
        # Importance Multiplier: Critical assets boost the risk score
        # Score 10 -> 1.5x risk, Score 5 -> 1.0x risk
        importance_multiplier = 1.0 + (target['importance'] - 5) * 0.1

    # C. Construct Prompt
    weather_context = "N/A"
    if weather_data:
        weather_context = f"{weather_data.get('condition')}, Wind: {weather_data.get('wind_speed_ms')}m/s"

    prompt = f"""
    You are a Security Operations Center AI.
    
    TARGET ASSET: {primary_asset_context}
    
    LOCAL WEATHER: {weather_context}
    
    NEWS ALERT:
    Headline: {article_input.get('headline')}
    Summary: {article_input.get('summary')}
    
    TASK:
    Assess if this news poses a physical or operational threat to the TARGET ASSET.
    - If the target is "General Supply Chain", be conservative.
    - If the target is a specific warehouse, be highly sensitive to physical threats (fire, riot, flood).
    - Estimate the "Impact Radius" of the event (e.g., a massive explosion might impact 10km, a petty theft 0km).
    """

    try:
        # D. Call LLM
        assessment = client.chat.completions.create(
            model="gpt-4o-mini",
            response_model=RiskAssessment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        
        result = assessment.model_dump()
        
        # E. Apply Importance Logic (The "Multiplier")
        # If it's a real threat (>20) AND it's a critical asset, boost the score.
        if result['risk_score'] > 20:
            result['risk_score'] = int(result['risk_score'] * importance_multiplier)
            # Cap at 100
            result['risk_score'] = min(result['risk_score'], 100)
            
        result['impacted_asset'] = primary_asset_context
        
        return result

    except Exception as e:
        return {
            "risk_score": 0,
            "severity": "ERROR",
            "reasoning": str(e),
            "action": "Check Logs",
            "impacted_asset": "System Error",
            "estimated_impact_radius": 0
        }
