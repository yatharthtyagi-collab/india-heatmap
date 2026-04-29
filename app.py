import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import json
import os

st.set_page_config(layout="wide")
st.title("India Business Heatmap")

# 👉 Your sheet (single Master sheet now)
SHEET_URL = "https://docs.google.com/spreadsheets/d/1MlQ3QyENQLA1CuuQkJiK9HwNBgKwa2I1AAdBDMbYaLc/export?format=csv&gid=1966151497"

CACHE_FILE = "geo_cache.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        return json.load(open(CACHE_FILE))
    return {}

def save_cache(cache):
    json.dump(cache, open(CACHE_FILE, "w"))

try:
    df = pd.read_csv(SHEET_URL)
    df.columns = df.columns.str.strip()

    # ✅ Required columns
    required_cols = [
        "Origin city",
        "Total Order",
        "Total Revenue",
        "Total Weight",
        "final_category",
        "final_sub_category"
    ]

    if not all(col in df.columns for col in required_cols):
        st.error("Sheet format mismatch. Check column names.")
        st.stop()

    # Clean data
    df["Origin city"] = df["Origin city"].astype(str).str.strip()
    df["Total Revenue"] = pd.to_numeric(df["Total Revenue"], errors="coerce").fillna(0)
    df["Total Order"] = pd.to_numeric(df["Total Order"], errors="coerce").fillna(0)
    df["Total Weight"] = pd.to_numeric(df["Total Weight"], errors="coerce").fillna(0)

    # =========================
    # 🎯 FILTERS
    # =========================
    st.subheader("Filters")

    col1, col2, col3 = st.columns(3)

    # Weight filter
    min_w, max_w = int(df["Total Weight"].min()), int(df["Total Weight"].max())
    weight_range = col1.slider("Total Weight", min_w, max_w, (min_w, max_w))

    # Category filter
    categories = ["All"] + sorted(df["final_category"].dropna().unique().tolist())
    selected_cat = col2.selectbox("Category", categories)

    # Sub-category filter
    sub_categories = ["All"] + sorted(df["final_sub_category"].dropna().unique().tolist())
    selected_subcat = col3.selectbox("Sub Category", sub_categories)

    # =========================
    # APPLY FILTERS
    # =========================
    filtered_df = df[
        (df["Total Weight"] >= weight_range[0]) &
        (df["Total Weight"] <= weight_range[1])
    ]

    if selected_cat != "All":
        filtered_df = filtered_df[filtered_df["final_category"] == selected_cat]

    if selected_subcat != "All":
        filtered_df = filtered_df[filtered_df["final_sub_category"] == selected_subcat]

    if filtered_df.empty:
        st.warning("No data after applying filters.")
        st.stop()

    # =========================
    # GROUP DATA
    # =========================
    city_data = filtered_df.groupby("Origin city").agg({
        "Total Revenue": "sum",
        "Total Order": "sum",
        "Total Weight": "sum"
    }).reset_index()

    # =========================
    # GEOLOCATION
    # =========================
    geolocator = Nominatim(user_agent="heatmap_app")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)

    cache = load_cache()

    def get_coords(city):
        query = f"{city}, India"
        if query in cache:
            return cache[query]

        loc = geocode(query)
        coords = (loc.latitude, loc.longitude) if loc else (None, None)
        cache[query] = coords
        return coords

    coords = [get_coords(city) for city in city_data["Origin city"]]
    city_data["lat"], city_data["lon"] = zip(*coords)
    city_data = city_data.dropna(subset=["lat"])

    save_cache(cache)

    # =========================
    # KPI CARDS
    # =========================
    col1, col2, col3 = st.columns(3)

    col1.metric("Total Revenue", f"₹{city_data['Total Revenue'].sum():,.0f}")
    col2.metric("Total Orders", f"{int(city_data['Total Order'].sum()):,}")
    col3.metric("Total Weight", f"{int(city_data['Total Weight'].sum()):,}")

    # =========================
    # MAP
    # =========================
    m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)

    heat_data = city_data[["lat", "lon", "Total Revenue"]].values.tolist()
    HeatMap(heat_data, radius=20, blur=15).add_to(m)

    for _, row in city_data.iterrows():
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=5,
            tooltip=row["Origin city"],
            popup=f"""
            <b>City:</b> {row['Origin city']}<br>
            <b>Revenue:</b> ₹{row['Total Revenue']:,.0f}<br>
            <b>Orders:</b> {int(row['Total Order']):,}<br>
            <b>Weight:</b> {int(row['Total Weight']):,}
            """
        ).add_to(m)

    st_folium(m, width=1400, height=650)

except Exception as e:
    st.error("Error loading data")
