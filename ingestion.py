import os
import requests
from dotenv import load_dotenv
from datetime import datetime
from geopy.geocoders import Nominatim

load_dotenv()

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

# --- FETCH FUNCTIONS (The "Raw" Data) ---

def fetch_weather(city_name):
    """Fetches current weather for a specific city name."""
    if not WEATHER_API_KEY:
        return {"error": "Missing Weather API Key in .env"}
    
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric"
    try:
        # TIMEOUT ADDED: Stops hanging after 10 seconds
        response = requests.get(url, timeout=10)
        response.raise_for_status() 
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def fetch_weather_coords(lat, lon):
    """Fetches weather using precise Lat/Lon coordinates."""
    if not WEATHER_API_KEY:
        return {"error": "Missing Weather API Key in .env"}
    
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def reverse_geocode(lat, lon):
    """Converts Lat/Lon -> City Name."""
    try:
        geolocator = Nominatim(user_agent="sentinel_risk_agent_v1", timeout=10)
        location = geolocator.reverse((lat, lon), language='en', exactly_one=True)
        
        if location:
            address = location.raw.get('address', {})
            return (address.get('city') or 
                    address.get('town') or 
                    address.get('village') or 
                    address.get('county') or
                    address.get('state_district'))
    except Exception as e:
        print(f"Geocoding error: {e}")
        return None
    return None

def fetch_news(topic, location=None):
    """Fetches news, strictly restricted to a specific location."""
    if not NEWS_API_KEY:
        return {"error": "Missing News API Key in .env"}
    
    if location:
        query = f"{topic} AND {location}"
    else:
        query = topic
        
    print(f"   --> Querying NewsAPI for: '{query}'...")

    url = (
        f"https://newsapi.org/v2/everything?"
        f"q={query}&"
        f"searchIn=title,description&"
        f"sortBy=publishedAt&"
        f"apiKey={NEWS_API_KEY}&"
        f"language=en&"
        f"pageSize=100"
    )
    
    try:
        # TIMEOUT ADDED
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"   [!] NewsAPI Error: {e}")
        return {"error": str(e)}

# --- PARSER FUNCTIONS (Unchanged) ---

def parse_weather_risk(api_response):
    if "error" in api_response:
        return api_response

    try:
        data = {
            "location": api_response.get("name"),
            "lat": api_response["coord"]["lat"],
            "lon": api_response["coord"]["lon"],
            "temp_c": api_response["main"]["temp"],
            "condition": api_response["weather"][0]["description"],
            "wind_speed_ms": api_response["wind"]["speed"],
            "visibility_km": api_response.get("visibility", 10000) / 1000
        }
        return data
    except Exception as e:
        return {"error": f"Parsing failed: {str(e)}"}

def parse_news_risk(api_response):
    if "error" in api_response:
        return []

    processed_articles = []
    # Simple list comp to filter empty articles
    raw_articles = [a for a in api_response.get("articles", []) if a.get("title")]

    for article in raw_articles:
        processed_articles.append({
            "Headline": article.get("title"),
            "Source": article.get("source", {}).get("name"),
            "Published": article.get("publishedAt", "")[:19].replace("T", " "),
            "URL": article.get("url"),
            "summary": article.get("description")
        })
            
    return processed_articles