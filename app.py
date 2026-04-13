import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import json
import os

st.set_page_config(page_title="India Business Heatmap", layout="wide")
st.title("India Business Heatmap")

SPREADSHEET_ID = "1MlQ3QyENQLA1CuuQkJiK9HwNBgKwa2I1AAdBDMbYaLc"

SHEETS = {
    "Sales": "2040027668",
    "Franchise": "0"
}

CACHE_FILE = "geo_cache.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

selected_sheet = st.radio("Select Department", ["Sales", "Franchise"], horizontal=True)

if st.button("Refresh Data"):
    st.rerun()

gid = SHEETS[selected_sheet]
sheet_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}"

try:
    df = pd.read_csv(sheet_url)

    # Clean column names
    df.columns = df.columns.str.strip()

    required_cols = ["State", "City", "Revenue", "Vendor count", "Order count"]
    missing_cols = [col for col in required_cols if col not in df.columns]

    if missing_cols:
        st.error(f"Missing columns in sheet: {', '.join(missing_cols)}")
        st.stop()

    # Clean values
    df["State"] = df["State"].astype(str).str.strip()
    df["City"] = df["City"].astype(str).str.strip()

    df["Revenue"] = pd.to_numeric(df["Revenue"], errors="coerce").fillna(0)
    df["Vendor count"] = pd.to_numeric(df["Vendor count"], errors="coerce").fillna(0)
    df["Order count"] = pd.to_numeric(df["Order count"], errors="coerce").fillna(0)

    # Aggregate by State + City
    city_data = (
        df.groupby(["State", "City"], as_index=False)
        .agg({
            "Revenue": "sum",
            "Vendor count": "sum",
            "Order count": "sum"
        })
    )

    geolocator = Nominatim(user_agent="india_business_heatmap_app")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
    cache = load_cache()

    def get_coords(state, city):
        query = f"{city}, {state}, India"

        if query in cache:
            return cache[query]

        location = geocode(query, timeout=10)
        if location:
            coords = [location.latitude, location.longitude]
        else:
            coords = [None, None]

        cache[query] = coords
        return coords

    progress_bar = st.progress(0)
    status_box = st.empty()

    coords = []
    total = len(city_data)

    for i, row in city_data.iterrows():
        state = row["State"]
        city = row["City"]
        status_box.text(f"Processing {i+1}/{total}: {city}, {state}")
        coords.append(get_coords(state, city))
        progress_bar.progress((i + 1) / total)

    save_cache(cache)

    city_data["lat"] = [c[0] for c in coords]
    city_data["lon"] = [c[1] for c in coords]
    city_data = city_data.dropna(subset=["lat", "lon"])

    progress_bar.empty()
    status_box.success(f"{selected_sheet} data loaded successfully")

    if city_data.empty:
        st.warning("No valid map locations found.")
        st.stop()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Revenue", f"₹{city_data['Revenue'].sum():,.0f}")
    col2.metric("Total Orders", f"{int(city_data['Order count'].sum()):,}")
    col3.metric("Total Vendors", f"{int(city_data['Vendor count'].sum()):,}")

    st.subheader(f"Showing: {selected_sheet}")

    m = folium.Map(
        location=[20.5937, 78.9629],
        zoom_start=5,
        tiles="CartoDB positron"
    )

    heat_data = city_data[["lat", "lon", "Revenue"]].values.tolist()
    HeatMap(heat_data, radius=22, blur=18).add_to(m)

    for _, row in city_data.iterrows():
        popup_html = f"""
        <b>State:</b> {row['State']}<br>
        <b>City:</b> {row['City']}<br>
        <b>Revenue:</b> ₹{row['Revenue']:,.0f}<br>
        <b>Vendor count:</b> {int(row['Vendor count']):,}<br>
        <b>Order count:</b> {int(row['Order count']):,}
        """

        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=5,
            tooltip=f"{row['City']}, {row['State']}",
            popup=popup_html,
            color="#3186cc",
            fill=True,
            fill_color="#3186cc",
            fill_opacity=0.65
        ).add_to(m)

    st_folium(m, width=1400, height=650)

except Exception:
    st.error("Unable to load or process the Google Sheet. Please check the sheet data and sharing settings.")