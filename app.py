import streamlit as st
import pandas as pd
from ingestion import fetch_weather_coords, fetch_news, parse_weather_risk, parse_news_risk, reverse_geocode
from risk_engine import assess_news_risk, update_asset_registry
import folium
from streamlit_folium import st_folium
from folium import plugins
from database import (
    sign_in_user, sign_up_user, sign_out_user,
    save_asset, get_user_assets, delete_asset, 
    save_analysis, bulk_save_assets, get_latest_analysis, get_threats_for_analysis
)

st.set_page_config(page_title="AI Risk Agent", layout="wide", initial_sidebar_state="expanded")

# Custom CSS
st.markdown("""
<style>
    .stApp {
        background-color: #0a0a0a;
    }
</style>
""", unsafe_allow_html=True)

# --- STATE MANAGEMENT ---
if "user" not in st.session_state: st.session_state.user = None
if "page" not in st.session_state: st.session_state.page = "input"
if "assets" not in st.session_state: st.session_state.assets = []
if "analysis_results" not in st.session_state: st.session_state.analysis_results = {}
if "selected_asset_index" not in st.session_state: st.session_state.selected_asset_index = None
if "dashboard_tab" not in st.session_state: st.session_state.dashboard_tab = "overview"
# FIX 1: Add a flag to track if we forced a new analysis
if "fresh_analysis_triggered" not in st.session_state: st.session_state.fresh_analysis_triggered = False

# --- AUTH LOGIC ---
if st.session_state.user is None:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🛡️ Sentinel Login")
        st.markdown("Secure Corporate Risk Intelligence Platform")
        
        tab1, tab2 = st.tabs(["Login", "Sign Up"])
        
        with tab1:
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                submit = st.form_submit_button("Sign In", type="primary", use_container_width=True)
                
                if submit:
                    user = sign_in_user(email, password)
                    if user:
                        st.session_state.user = user
                        st.success("Login successful!")
                        st.rerun()
                    else:
                        st.error("Invalid credentials.")

        with tab2:
            with st.form("signup_form"):
                new_email = st.text_input("Email")
                new_password = st.text_input("Password", type="password")
                confirm = st.text_input("Confirm Password", type="password")
                submit_up = st.form_submit_button("Create Account", use_container_width=True)
                
                if submit_up:
                    if new_password != confirm:
                        st.error("Passwords do not match.")
                    else:
                        user = sign_up_user(new_email, new_password)
                        if user:
                            st.success("Account created! Please sign in.")
                        else:
                            st.error("Signup failed. Email might be in use.")
else:
    # Sidebar Navigation
    with st.sidebar:
        st.markdown(f"<h3>{st.session_state.user.email}</h3>", unsafe_allow_html=True)
        
        if st.button("Logout", use_container_width=True):
            sign_out_user()
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        
        st.divider()
        
        if st.session_state.page == "input":
            st.markdown("<h4>Asset Configuration</h4>", unsafe_allow_html=True)
        else:
            st.markdown("<h4>Dashboard Navigation</h4>", unsafe_allow_html=True)
            
            if st.button("Overview", use_container_width=True, type="primary" if st.session_state.dashboard_tab == "overview" else "secondary"):
                st.session_state.dashboard_tab = "overview"
                st.rerun()
            
            if st.button("Alerts", use_container_width=True, type="primary" if st.session_state.dashboard_tab == "alerts" else "secondary"):
                st.session_state.dashboard_tab = "alerts"
                st.rerun()
            
            if st.button("Assets", use_container_width=True, type="primary" if st.session_state.dashboard_tab == "assets" else "secondary"):
                st.session_state.dashboard_tab = "assets"
                st.rerun()
            
            if st.button("Data Sources", use_container_width=True, type="primary" if st.session_state.dashboard_tab == "sources" else "secondary"):
                st.session_state.dashboard_tab = "sources"
                st.rerun()
            
            if st.button("Risk Trends", use_container_width=True, type="primary" if st.session_state.dashboard_tab == "trends" else "secondary"):
                st.session_state.dashboard_tab = "trends"
                st.rerun()
            
            st.divider()
            
            if st.button("← Back to Config", use_container_width=True):
                st.session_state.analysis_results = {}
                st.session_state.page = "input"
                st.rerun()

    # Load assets from database on first load
    if not st.session_state.assets:
        db_assets = get_user_assets(st.session_state.user.id)
        if db_assets:
            st.session_state.assets = [
                {
                    "id": a.get('id'),
                    "name": a['name'],
                    "type": a['type'],
                    "lat": float(a['lat']) if a['lat'] else None,
                    "lon": float(a['lon']) if a['lon'] else None,
                    "importance": a['importance'],
                    "radius": a['radius']
                }
                for a in db_assets
            ]

    if st.session_state.page == "input":
        st.title("Asset Configuration Portal")
        st.markdown("Configure your assets and their locations before running multi-site risk analysis.")
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("Asset Registry")
            
            if st.button("Add New Asset", type="primary", use_container_width=True):
                new_asset = {
                    "id": None,
                    "name": f"Asset {len(st.session_state.assets) + 1}",
                    "type": "Warehouse",
                    "lat": None,
                    "lon": None,
                    "importance": 5,
                    "radius": 10
                }
                st.session_state.assets.append(new_asset)
                st.rerun()
            
            st.divider()
            
            if not st.session_state.assets:
                st.info("👆 Click 'Add New Asset' to begin configuring your assets.")
            else:
                for idx, asset in enumerate(st.session_state.assets):
                    with st.expander(f"{asset['name']}", expanded=(idx == len(st.session_state.assets) - 1)):
                        col_a, col_b = st.columns([3, 1])
                        
                        with col_a:
                            asset['name'] = st.text_input(
                                "Asset Name",
                                value=asset['name'],
                                key=f"name_{idx}",
                                placeholder="e.g., Mumbai Central Warehouse"
                            )
                        
                        with col_b:
                            if st.button("🗑️ Delete", key=f"del_{idx}", use_container_width=True):
                                if asset.get('id'):
                                    delete_asset(asset['id'])
                                st.session_state.assets.pop(idx)
                                st.rerun()
                        
                        asset['type'] = st.selectbox(
                            "Asset Type",
                            ["Warehouse", "Distribution Center", "Headquarters", "Port", "Factory", "Retail Store", "Logistics Hub"],
                            index=["Warehouse", "Distribution Center", "Headquarters", "Port", "Factory", "Retail Store", "Logistics Hub"].index(asset['type']) if asset['type'] in ["Warehouse", "Distribution Center", "Headquarters", "Port", "Factory", "Retail Store", "Logistics Hub"] else 0,
                            key=f"type_{idx}"
                        )
                        
                        col_c, col_d = st.columns(2)
                        with col_c:
                            asset['importance'] = st.slider(
                                "Criticality Level",
                                1, 10, asset['importance'],
                                key=f"imp_{idx}",
                                help="1 = Low priority, 10 = Mission critical"
                            )
                        with col_d:
                            asset['radius'] = st.number_input(
                                "Monitor Radius (km)",
                                1, 100, asset['radius'],
                                key=f"rad_{idx}",
                                help="Events within this radius will trigger alerts"
                            )
                        
                        if st.button("Save Changes", key=f"save_{idx}", use_container_width=True):
                            if asset['lat'] is not None and asset['lon'] is not None:
                                saved = save_asset(asset, st.session_state.user.id)
                                if saved:
                                    asset['id'] = saved['id']
                                    st.success(f"Saved {asset['name']} to database!")
                                    st.rerun()
                                else:
                                    st.error("Failed to save. Check database connection.")
                            else:
                                st.warning("⚠️ Set location first before saving")
                        
                        if asset['lat'] is None or asset['lon'] is None:
                            st.warning("Location not set. Click this asset's marker on the map to set location.")
                            if st.button("Set Location on Map", key=f"loc_{idx}", use_container_width=True):
                                st.session_state.selected_asset_index = idx
                                st.info("Now click on the map to pin this asset's location")
                        else:
                            st.success(f"Location: {asset['lat']:.4f}, {asset['lon']:.4f}")
                            if st.button("Change Location", key=f"change_{idx}", use_container_width=True):
                                st.session_state.selected_asset_index = idx
                                st.info("Click on the map to update location")
        
        with col2:
            st.subheader("Asset Location Map")
            
            if st.session_state.selected_asset_index is not None:
                st.info(f"Click map to set location for: **{st.session_state.assets[st.session_state.selected_asset_index]['name']}**")
            
            if st.session_state.assets and any(a['lat'] is not None for a in st.session_state.assets):
                valid_assets = [a for a in st.session_state.assets if a['lat'] is not None]
                center_lat = sum(a['lat'] for a in valid_assets) / len(valid_assets)
                center_lon = sum(a['lon'] for a in valid_assets) / len(valid_assets)
                zoom = 8
            else:
                center_lat, center_lon, zoom = 20.5937, 78.9629, 5
            
            m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom)
            m.add_child(folium.LatLngPopup())
            
            for idx, asset in enumerate(st.session_state.assets):
                if asset['lat'] is not None and asset['lon'] is not None:
                    color = "red" if asset['importance'] >= 8 else "orange" if asset['importance'] >= 5 else "green"
                    
                    folium.Marker(
                        [asset['lat'], asset['lon']],
                        popup=f"<b>{asset['name']}</b><br>{asset['type']}<br>Importance: {asset['importance']}/10",
                        tooltip=asset['name'],
                        icon=folium.Icon(color=color, icon="building", prefix='fa')
                    ).add_to(m)
                    
                    folium.Circle(
                        [asset['lat'], asset['lon']],
                        radius=asset['radius'] * 1000,
                        color=color,
                        fill=True,
                        fillOpacity=0.1,
                        weight=1
                    ).add_to(m)
            
            map_data = st_folium(m, height=600, width="100%")
            
            if map_data and map_data['last_clicked'] and st.session_state.selected_asset_index is not None:
                clicked_lat = map_data['last_clicked']['lat']
                clicked_lng = map_data['last_clicked']['lng']
                
                st.session_state.assets[st.session_state.selected_asset_index]['lat'] = clicked_lat
                st.session_state.assets[st.session_state.selected_asset_index]['lon'] = clicked_lng
                
                city = reverse_geocode(clicked_lat, clicked_lng)
                if city and "Asset" in st.session_state.assets[st.session_state.selected_asset_index]['name']:
                    st.session_state.assets[st.session_state.selected_asset_index]['name'] = f"{city} {st.session_state.assets[st.session_state.selected_asset_index]['type']}"
                
                asset_to_save = st.session_state.assets[st.session_state.selected_asset_index]
                saved = save_asset(asset_to_save, st.session_state.user.id)
                if saved:
                    st.session_state.assets[st.session_state.selected_asset_index]['id'] = saved['id']
                
                st.session_state.selected_asset_index = None
                st.rerun()
        
        st.divider()
        col_bottom1, col_bottom2, col_bottom3 = st.columns([2, 2, 1])
        
        with col_bottom1:
            risk_topic = st.text_input(
                "Risk Topic to Monitor",
                value="logistics",
                help="Keywords for news search"
            )
        
        with col_bottom2:
            st.metric("Total Assets Configured", len(st.session_state.assets))
            ready_count = sum(1 for a in st.session_state.assets if a['lat'] is not None)
            st.metric("Assets with Locations", ready_count)
        
        with col_bottom3:
            st.write("")
            st.write("")
            if ready_count == 0:
                st.button("Analyze All Assets", disabled=True, use_container_width=True)
                st.caption("⚠️ Set at least 1 asset location")
            else:
                if st.button("Analyze All Assets", type="primary", use_container_width=True):
                    for asset in st.session_state.assets:
                        if asset['lat'] is not None and asset['lon'] is not None:
                            saved = save_asset(asset, st.session_state.user.id)
                            if saved and not asset.get('id'):
                                asset['id'] = saved['id']
                    
                    st.session_state.risk_topic = risk_topic
                    st.session_state.analysis_results = {}
                    # FIX 2: Set flag to True so hydration logic knows to skip DB and run fresh
                    st.session_state.fresh_analysis_triggered = True
                    
                    st.session_state.page = "analysis"
                    st.rerun()

    elif st.session_state.page == "analysis":
        
        # FIX 3: Auto-hydration logic checks if we are NOT in a fresh trigger mode
        if not st.session_state.analysis_results and not st.session_state.fresh_analysis_triggered:
            with st.spinner("Restoring session data..."):
                results = {}
                if "risk_topic" not in st.session_state:
                    st.session_state.risk_topic = "General Supply Chain" 

                for asset in st.session_state.assets:
                    if not asset.get('id'):
                        continue
                    
                    latest = get_latest_analysis(asset['id'])
                    
                    if latest:
                        st.session_state.risk_topic = latest.get('risk_topic', st.session_state.risk_topic)
                        threats = get_threats_for_analysis(latest['id'])
                        
                        articles = []
                        for threat in threats:
                            articles.append({
                                'Headline': threat['headline'],
                                'Source': threat['source'],
                                'Published': threat['published_date'],
                                'URL': threat['url'],
                                'risk_score': threat['risk_score'],
                                'severity': threat['severity'],
                                'reasoning': threat['reasoning'],
                                'action': threat['action'],
                                'impacted_asset': threat['impacted_asset']
                            })
                        
                        import json
                        weather = json.loads(latest['weather_data']) if latest['weather_data'] else {}
                        
                        results[asset['name']] = {
                            'asset': asset,
                            'weather': weather,
                            'articles': articles,
                            'max_risk': latest['max_risk_score']
                        }
                
                if results:
                    st.session_state.analysis_results = results
        
        # Run analysis if needed (either empty results or we explicitly cleared them)
        if not st.session_state.analysis_results:
            progress_bar = st.progress(0, text="Initializing multi-site analysis...")
            
            update_asset_registry(st.session_state.assets)
            
            results = {}
            total_steps = len(st.session_state.assets)
            
            for idx, asset in enumerate(st.session_state.assets):
                if asset['lat'] is None or asset['lon'] is None:
                    continue
                
                progress_bar.progress((idx + 1) / total_steps, text=f"Analyzing {asset['name']}...")
                
                weather_raw = fetch_weather_coords(asset['lat'], asset['lon'])
                weather_clean = parse_weather_risk(weather_raw)
                
                city = reverse_geocode(asset['lat'], asset['lon'])
                
                news_raw = fetch_news(st.session_state.risk_topic, location=city)
                articles = parse_news_risk(news_raw)
                
                if not articles or len(articles) < 3:
                    news_raw_broad = fetch_news(st.session_state.risk_topic, location=None)
                    articles_broad = parse_news_risk(news_raw_broad)
                    articles = articles_broad if len(articles_broad) > len(articles) else articles
                
                enhanced_articles = []
                if articles:
                    for art in articles[:10]:
                        ai_input = {"headline": art["Headline"], "summary": art.get("summary", art["Headline"])}
                        assessment = assess_news_risk(ai_input, weather_data=weather_clean)
                        art.update(assessment)
                        enhanced_articles.append(art)
                
                max_risk = max([a['risk_score'] for a in enhanced_articles], default=0)
                
                results[asset['name']] = {
                    'asset': asset,
                    'weather': weather_clean,
                    'articles': enhanced_articles,
                    'max_risk': max_risk
                }
                
                if asset.get('id'):
                    save_analysis(
                        asset_id=asset['id'],
                        risk_topic=st.session_state.risk_topic,
                        weather_data=weather_clean,
                        articles=enhanced_articles,
                        max_risk_score=max_risk
                    )
            
            progress_bar.empty()
            st.session_state.analysis_results = results
            # FIX 4: Reset the flag so future page reloads will use the DB
            st.session_state.fresh_analysis_triggered = False
            st.rerun()
        
        results = st.session_state.analysis_results
        
        # OVERVIEW TAB
        if st.session_state.dashboard_tab == "overview":
            st.title("Risk Overview Dashboard")
            st.markdown(f"Monitoring **{len(st.session_state.assets)}** assets for: `{st.session_state.risk_topic}`")
            
            # Global metrics
            total_threats = sum(len(r['articles']) for r in results.values())
            avg_risk = sum(r['max_risk'] for r in results.values()) / len(results) if results else 0
            critical_assets = sum(1 for r in results.values() if r['max_risk'] > 75)
            high_risk_assets = sum(1 for r in results.values() if 40 < r['max_risk'] <= 75)
            
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Total Threats", total_threats)
            m2.metric("Avg Risk Score", f"{int(avg_risk)}/100")
            m3.metric("Critical Sites", critical_assets)
            m4.metric("High Risk Sites", high_risk_assets)
            m5.metric("Safe Sites", len(results) - critical_assets - high_risk_assets)
            
            st.divider()
            
            # Two-column layout for map and top alerts
            col_map, col_alerts = st.columns([1.5, 1])
            
            with col_map:
                st.markdown("### Global Risk Map")
                
                all_lats = [a['lat'] for a in st.session_state.assets if a['lat']]
                all_lons = [a['lon'] for a in st.session_state.assets if a['lon']]
                center_lat = sum(all_lats) / len(all_lats)
                center_lon = sum(all_lons) / len(all_lons)
                
                global_map = folium.Map(location=[center_lat, center_lon], zoom_start=6, tiles="CartoDB dark_matter")
                
                for asset_name, result in results.items():
                    asset = result['asset']
                    risk = result['max_risk']
                    
                    if risk > 75:
                        color = "red"
                    elif risk > 40:
                        color = "orange"
                    else:
                        color = "green"
                    
                    folium.Marker(
                        [asset['lat'], asset['lon']],
                        popup=f"<b>{asset['name']}</b><br>Risk: {risk}/100<br>{len(result['articles'])} threats",
                        tooltip=f"{asset['name']} - Risk: {risk}",
                        icon=folium.Icon(color=color, icon="warning" if risk > 40 else "info-sign")
                    ).add_to(global_map)
                    
                    folium.Circle(
                        [asset['lat'], asset['lon']],
                        radius=asset['radius'] * 1000,
                        color=color,
                        fill=True,
                        fillOpacity=0.3,
                        weight=2
                    ).add_to(global_map)
                
                st_folium(global_map, height=400, width="100%")
            
            with col_alerts:
                st.markdown("### Top Critical Alerts")
                
                # Collect and sort all alerts
                all_alerts = []
                for asset_name, result in results.items():
                    for article in result['articles']:
                        all_alerts.append({
                            'asset': asset_name,
                            'article': article
                        })
                
                all_alerts.sort(key=lambda x: x['article']['risk_score'], reverse=True)
                
                if not all_alerts:
                    st.success("No active threats")
                else:
                    # Show top 3 critical alerts
                    for alert in all_alerts[:3]:
                        article = alert['article']
                        score = article['risk_score']
                        
                        if score > 75:
                            color = "#D32F2F"
                            emoji = "🔴"
                        elif score > 40:
                            color = "#FF6F00"
                            emoji = "🟠"
                        else:
                            color = "#00C853"
                            emoji = "🟢"
                        
                        st.markdown(f"""
                        <div style="
                            border-left: 4px solid {color};
                            padding: 12px;
                            background: #1a1a1a;
                            margin-bottom: 12px;
                            border-radius: 4px;
                        ">
                            <div style="color: white; font-weight: bold; margin-bottom: 5px;">
                                {emoji} {score}/100
                            </div>
                            <div style="color: white; font-size: 14px; margin-bottom: 5px;">
                                {article['Headline'][:80]}...
                            </div>
                            <div style="color: #999; font-size: 12px;">
                                {alert['asset']}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    if len(all_alerts) > 3:
                        st.caption(f"+ {len(all_alerts) - 3} more alerts")
            
            st.divider()
            
            # Two-column layout for Environmental Conditions and Risk Status
            col_weather, col_risk = st.columns([1, 1])
            
            with col_weather:
                st.markdown("### Environmental Conditions")
                
                for asset_name, result in results.items():
                    weather = result['weather']
                    st.markdown(f"**{asset_name}**")
                    
                    wcol1, wcol2, wcol3, wcol4 = st.columns(4)
                    with wcol1:
                        st.metric("🌡️", f"{weather.get('temp_c', 0)}°C")
                    with wcol2:
                        st.metric("💨", f"{weather.get('wind_speed_ms', 0)} m/s")
                    with wcol3:
                        st.metric("👁️", f"{weather.get('visibility_km', 0)} km")
                    with wcol4:
                        st.caption(f"**{weather.get('condition', 'N/A')}**")
                    

            
            with col_risk:
                st.markdown("### Asset Risk Status")
                
                sorted_results = sorted(results.items(), key=lambda x: x[1]['max_risk'], reverse=True)
                
                for asset_name, result in sorted_results:
                    asset = result['asset']
                    max_risk = result['max_risk']
                    articles = result['articles']
                    
                    if max_risk > 75:
                        status_color = "#D32F2F"
                        status = "🔴 CRITICAL"
                    elif max_risk > 40:
                        status_color = "#FF6F00"
                        status = "🟠 HIGH RISK"
                    else:
                        status_color = "#00C853"
                        status = "🟢 SAFE"
                    
                    st.markdown(f"""
                    <div style="
                        border: 2px solid {status_color};
                        border-radius: 8px;
                        padding: 15px;
                        background: linear-gradient(135deg, #1e1e1e 0%, #2d2d2d 100%);
                        margin-bottom: 15px;
                    ">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <h3 style="margin: 0; color: white;">{asset['name']}</h3>
                                <p style="margin: 5px 0; color: #999;">{len(articles)} threats detected</p>
                            </div>
                            <div style="text-align: right;">
                                <div style="color: {status_color}; font-size: 24px; font-weight: bold;">{max_risk}/100</div>
                                <div style="color: {status_color}; font-size: 12px;">{status}</div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            
            st.divider()
            
            # Recent Articles Preview
            st.markdown("### Recent Threat Intelligence")
            
            # Show 2 most recent high-risk articles from any asset
            recent_articles = []
            for asset_name, result in results.items():
                for article in result['articles']:
                    if article['risk_score'] > 40:
                        recent_articles.append({
                            'asset': asset_name,
                            'article': article
                        })
            
            recent_articles.sort(key=lambda x: x['article']['risk_score'], reverse=True)
            
            if recent_articles:
                for item in recent_articles[:2]:
                    article = item['article']
                    score = article['risk_score']
                    
                    col_a, col_b = st.columns([3, 1])
                    
                    with col_a:
                        st.markdown(f"**{article['Headline']}**")
                        st.caption(f"🏢 {item['asset']} • 📰 {article['Source']} • 📅 {article['Published']}")
                        st.markdown(f"_{article['reasoning'][:150]}..._")
                    
                    with col_b:
                        if score > 75:
                            st.error(f"🔴 {score}/100")
                        elif score > 40:
                            st.warning(f"🟠 {score}/100")
                    
                    st.divider()
                
                st.caption(f"View all {len(all_alerts)} alerts in the Alerts tab")
            else:
                st.success("No high-risk threats detected")
        
        # ALERTS TAB
        elif st.session_state.dashboard_tab == "alerts":
            st.title("Active Alerts")
            
            # Collect all alerts
            all_alerts = []
            for asset_name, result in results.items():
                for article in result['articles']:
                    all_alerts.append({
                        'asset': asset_name,
                        'article': article
                    })
            
            all_alerts.sort(key=lambda x: x['article']['risk_score'], reverse=True)
            
            if not all_alerts:
                st.success("No active threats detected across all assets.")
            else:
                st.markdown(f"**{len(all_alerts)} total alerts** across all monitored assets")
                st.divider()
                
                # Show only top 3 initially
                show_count = st.session_state.get('show_all_alerts', 3)
                
                for idx, alert in enumerate(all_alerts[:show_count]):
                    article = alert['article']
                    score = article['risk_score']
                    
                    if score > 75:
                        color = "#D32F2F"
                        risk_label = "CRITICAL"
                        emoji = "🔴"
                    elif score > 40:
                        color = "#FF6F00"
                        risk_label = "HIGH"
                        emoji = "🟠"
                    else:
                        color = "#00C853"
                        risk_label = "LOW"
                        emoji = "🟢"
                    
                    st.markdown(f"""
                    <div style="
                        border: 2px solid {color};
                        border-radius: 8px;
                        padding: 20px;
                        background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
                        margin-bottom: 20px;
                    ">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <h3 style="margin: 0; color: white; flex: 1;">{emoji} {article['Headline']}</h3>
                            <div style="background-color: {color}; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold;">
                                {risk_label}: {score}/100
                            </div>
                        </div>
                        <div style="color: #999; font-size: 13px; margin-bottom: 10px;">
                            {alert['asset']} • {article['Source']} • {article['Published']}
                        </div>
                        <div style="color: white; margin-top: 10px;">
                            <strong>Analysis:</strong> {article['reasoning']}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                if len(all_alerts) > 3 and show_count == 3:
                    if st.button("Show All Alerts", use_container_width=True):
                        st.session_state.show_all_alerts = len(all_alerts)
                        st.rerun()
                elif show_count > 3:
                    if st.button("Show Less", use_container_width=True):
                        st.session_state.show_all_alerts = 3
                        st.rerun()
        
        # ASSETS TAB
        elif st.session_state.dashboard_tab == "assets":
            st.title("Asset Details")
            
            sorted_results = sorted(results.items(), key=lambda x: x[1]['max_risk'], reverse=True)
            
            for asset_name, result in sorted_results:
                asset = result['asset']
                weather = result['weather']
                max_risk = result['max_risk']
                
                if max_risk > 75:
                    border_color = "#D32F2F"
                    risk_label = "🔴 CRITICAL"
                elif max_risk > 40:
                    border_color = "#FF6F00"
                    risk_label = "🟠 HIGH RISK"
                else:
                    border_color = "#00C853"
                    risk_label = "🟢 SAFE"
                
                st.markdown(f"""
                <div style="
                    border: 3px solid {border_color};
                    border-radius: 10px;
                    padding: 20px;
                    background: linear-gradient(135deg, #1e1e1e 0%, #2d2d2d 100%);
                    margin-bottom: 20px;
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <h2 style="margin: 0; color: white;">{asset['name']}</h2>
                            <p style="margin: 5px 0; color: #999;">{asset['type']} • Criticality: {asset['importance']}/10</p>
                        </div>
                        <div style="background-color: {border_color}; padding: 15px 30px; border-radius: 10px; text-align: center;">
                            <div style="color: white; font-size: 24px; font-weight: bold;">{max_risk}/100</div>
                            <div style="color: white; font-size: 12px;">{risk_label}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Weather Details
                st.markdown("### Environmental Context")
                
                col1, col2, col3, col4, col5 = st.columns(5)
                
                with col1:
                    st.metric("Location", weather.get('location', 'N/A'))
                with col2:
                    st.metric("Temperature", f"{weather.get('temp_c', 0)}°C")
                with col3:
                    st.metric("Wind Speed", f"{weather.get('wind_speed_ms', 0)} m/s")
                with col4:
                    st.metric("Visibility", f"{weather.get('visibility_km', 0)} km")
                with col5:
                    st.metric("Condition", weather.get('condition', 'N/A'))
                
                st.divider()
        
        # DATA SOURCES TAB
        elif st.session_state.dashboard_tab == "sources":
            st.title("Data Sources")
            
            st.markdown("### Weather Intelligence")
            for asset_name, result in results.items():
                weather = result['weather']
                with st.expander(f"{asset_name} - Weather Data"):
                    st.json(weather)
            
            st.divider()
            
            st.markdown("### News Intelligence")
            for asset_name, result in results.items():
                articles = result['articles']
                with st.expander(f"{asset_name} - {len(articles)} News Sources"):
                    for article in articles[:5]:
                        st.markdown(f"**{article['Headline']}**")
                        st.caption(f"{article['Source']} • {article['Published']}")
                        st.markdown(f"[Read Article]({article['URL']})")
                        st.divider()
        
        # RISK TRENDS TAB
        elif st.session_state.dashboard_tab == "trends":
            st.title("Risk Score Trends")
            
            import plotly.graph_objects as go
            
            # Prepare data
            asset_names = []
            risk_scores = []
            threat_counts = []
            
            for asset_name, result in results.items():
                asset_names.append(asset_name)
                risk_scores.append(result['max_risk'])
                threat_counts.append(len(result['articles']))
            
            # Risk Score Line Chart
            fig1 = go.Figure(data=[
                go.Scatter(
                    x=asset_names,
                    y=risk_scores,
                    mode='lines+markers',
                    line=dict(color='#2196F3', width=3),
                    marker=dict(
                        size=12,
                        color=['#D32F2F' if r > 75 else '#FF6F00' if r > 40 else '#00C853' for r in risk_scores],
                        line=dict(color='white', width=2)
                    ),
                    text=risk_scores,
                    textposition='top center',
                )
            ])
            
            fig1.update_layout(
                title="Risk Scores by Asset",
                xaxis_title="Asset",
                yaxis_title="Risk Score",
                plot_bgcolor='#1a1a1a',
                paper_bgcolor='#0a0a0a',
                font=dict(color='white'),
                height=400
            )
            
            st.plotly_chart(fig1, use_container_width=True)
            
            st.divider()
            
            # Threat Count Line Chart
            fig2 = go.Figure(data=[
                go.Scatter(
                    x=asset_names,
                    y=threat_counts,
                    mode='lines+markers',
                    line=dict(color='#4CAF50', width=3),
                    marker=dict(
                        size=12,
                        color='#2196F3',
                        line=dict(color='white', width=2)
                    ),
                    text=threat_counts,
                    textposition='top center',
                )
            ])
            
            fig2.update_layout(
                title="Threat Count by Asset",
                xaxis_title="Asset",
                yaxis_title="Number of Threats",
                plot_bgcolor='#1a1a1a',
                paper_bgcolor='#0a0a0a',
                font=dict(color='white'),
                height=400
            )
            
            st.plotly_chart(fig2, use_container_width=True)
            
            st.divider()
            
            # Risk Distribution Pie Chart
            critical = sum(1 for r in results.values() if r['max_risk'] > 75)
            high = sum(1 for r in results.values() if 40 < r['max_risk'] <= 75)
            low = len(results) - critical - high
            
            fig3 = go.Figure(data=[
                go.Pie(
                    labels=['Critical', 'High Risk', 'Safe'],
                    values=[critical, high, low],
                    marker_colors=['#D32F2F', '#FF6F00', '#00C853'],
                    hole=0.3
                )
            ])
            
            fig3.update_layout(
                title="Risk Distribution",
                plot_bgcolor='#1a1a1a',
                paper_bgcolor='#0a0a0a',
                font=dict(color='white'),
                height=400
            )
            
            st.plotly_chart(fig3, use_container_width=True)