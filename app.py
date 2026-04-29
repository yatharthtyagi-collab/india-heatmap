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

SHEET_URL = "https://docs.google.com/spreadsheets/d/1MlQ3QyENQLA1CuuQkJiK9HwNBgKwa2I1AAdBDMbYaLc/export?format=csv&gid=1966151497"

CACHE_FILE = "geo_cache.json"

# =========================
# CACHE
# =========================
def load_cache():
    if os.path.exists(CACHE_FILE):
        return json.load(open(CACHE_FILE))
    return {}

def save_cache(cache):
    json.dump(cache, open(CACHE_FILE, "w"))

# =========================
# CLEAN FUNCTION
# =========================
def clean_numeric(col):
    return (
        col.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("₹", "", regex=False)
        .str.strip()
    )

try:
    df = pd.read_csv(SHEET_URL)
    df.columns = df.columns.str.strip()

    required_cols = [
        "Origin city",
        "vendor_id",
        "Total Order",
        "Total Revenue",
        "Total Weight",
        "Avg_Weight_per_order",
        "final_category",
        "final_sub_category"
    ]

    if not all(col in df.columns for col in required_cols):
        st.error("Sheet format mismatch.")
        st.stop()

    # =========================
    # CLEAN DATA
    # =========================
    df["Origin city"] = df["Origin city"].astype(str).str.strip()

    df["Total Revenue"] = pd.to_numeric(clean_numeric(df["Total Revenue"]), errors="coerce").fillna(0)
    df["Total Order"] = pd.to_numeric(clean_numeric(df["Total Order"]), errors="coerce").fillna(0)
    df["Total Weight"] = pd.to_numeric(clean_numeric(df["Total Weight"]), errors="coerce").fillna(0)
    df["Avg_Weight_per_order"] = pd.to_numeric(clean_numeric(df["Avg_Weight_per_order"]), errors="coerce").fillna(0)

    # =========================
    # FILTER UI
    # =========================
    st.subheader("Filters")

    col1, col2, col3, col4, col5 = st.columns(5)

    # Weight
    min_w, max_w = int(df["Total Weight"].min()), int(df["Total Weight"].max())
    weight_min = col1.number_input("Weight Min", value=min_w)
    weight_max = col1.number_input("Weight Max", value=max_w)

    # Vendor Orders (KEEP THIS)
    min_v, max_v = int(df["Total Order"].min()), int(df["Total Order"].max())
    vendor_min = col2.number_input("Vendor Orders Min", value=min_v)
    vendor_max = col2.number_input("Vendor Orders Max", value=max_v)

    # Avg Weight / Order
    min_avg, max_avg = int(df["Avg_Weight_per_order"].min()), int(df["Avg_Weight_per_order"].max())
    avg_min = col3.number_input("Avg Wt/Order Min(Kg)", value=min_avg)
    avg_max = col3.number_input("Avg Wt/Order Max(Kg)", value=max_avg)

    # Category
    categories = ["All"] + sorted(df["final_category"].dropna().unique().tolist())
    selected_cat = col4.selectbox("Category", categories)

    # Sub-category
    if selected_cat != "All":
        sub_df = df[df["final_category"] == selected_cat]
    else:
        sub_df = df

    sub_categories = ["All"] + sorted(sub_df["final_sub_category"].dropna().unique().tolist())
    selected_subcat = col5.selectbox("Sub Category", sub_categories)

    st.markdown("---")

    # =========================
    # VALIDATION
    # =========================
    if (weight_min > weight_max or 
        vendor_min > vendor_max or avg_min > avg_max):
        st.error("Min values cannot be greater than Max values")
        st.stop()

    # =========================
    # APPLY FILTERS (VENDOR LEVEL)
    # =========================
    filtered_df = df[
        (df["Total Order"] >= vendor_min) &
        (df["Total Order"] <= vendor_max) &
        (df["Avg_Weight_per_order"] >= avg_min) &
        (df["Avg_Weight_per_order"] <= avg_max)
    ]

    if selected_cat != "All":
        filtered_df = filtered_df[filtered_df["final_category"] == selected_cat]

    if selected_subcat != "All":
        filtered_df = filtered_df[filtered_df["final_sub_category"] == selected_subcat]

    if filtered_df.empty:
        st.warning("No data after vendor/category filters")
        st.stop()

    # =========================
    # KPI (CORRECT FIX)
    # =========================
    col1, col2, col3 = st.columns(3)

    col1.metric("Total Revenue", f"₹{filtered_df['Total Revenue'].sum():,.0f}")
    col2.metric("Total Orders", f"{int(filtered_df['Total Order'].sum()):,}")
    col3.metric("Total Weight", f"{int(filtered_df['Total Weight'].sum()):,}")

    st.caption(f"{filtered_df['Origin city'].nunique()} cities")

    # =========================
    # CITY AGGREGATION
    # =========================
    city_data = filtered_df.groupby("Origin city").agg({
        "Total Revenue": "sum",
        "Total Order": "sum",
        "Total Weight": "sum",
        "vendor_id": "nunique"
    }).reset_index()

    city_data.rename(columns={"vendor_id": "Vendor Count"}, inplace=True)

    # =========================
    # CITY FILTERS
    # =========================
    filtered_city = city_data[
        (city_data["Total Weight"] >= weight_min) &
        (city_data["Total Weight"] <= weight_max) 

    ]

    if filtered_city.empty:
        st.warning("No data for selected city filters")
        st.stop()

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

    coords = [get_coords(city) for city in filtered_city["Origin city"]]
    filtered_city["lat"], filtered_city["lon"] = zip(*coords)
    filtered_city = filtered_city.dropna(subset=["lat"])

    save_cache(cache)

    # =========================
    # MAP
    # =========================
    m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)

    heat_data = filtered_city[["lat", "lon", "Total Revenue"]].values.tolist()
    HeatMap(heat_data, radius=20, blur=15).add_to(m)

    for _, row in filtered_city.iterrows():
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=5,
            tooltip=row["Origin city"],
            popup=f"""
            <b>City:</b> {row['Origin city']}<br>
            <b>Revenue:</b> ₹{row['Total Revenue']:,.0f}<br>
            <b>Orders:</b> {int(row['Total Order']):,}<br>
            <b>Weight:</b> {int(row['Total Weight']):,}<br>
            <b>Vendors:</b> {int(row['Vendor Count'])}
            """
        ).add_to(m)

    st_folium(m, width=1400, height=650)

except Exception as e:
    st.error(f"Error loading data: {e}")
