"""
Geo Services Data Loader
========================
Downloads and loads the following datasets into PostGIS:

  1. Natural Earth 10m GeoPackage (global vector layers)
       → geo.countries      Country boundaries + population/economy data
       → geo.roads          Global road network
       → geo.rivers         Rivers and lake centerlines
       → geo.railroads      Global railroads
       → geo.places         Populated places

  2. World Bank Official Boundaries (Admin 1, Admin 2)
       → geo.provinces      Admin 1 regions  (authoritative WB boundaries)
       → geo.municipalities Admin 2 municipalities (new — not in Natural Earth)

       GeoPackages must be downloaded manually to data/ folder:
         data/wb_admin1.gpkg
         data/wb_admin2.gpkg
       Download from: https://datacatalog.worldbank.org/search/dataset/0038272

  3. OpenStreetMap Bulgaria via Geofabrik
       → geo.buildings      Building footprints
       → geo.pois           Points of interest (hospitals, schools etc.)
       → geo.natural_areas  National parks and nature reserves

Usage:
    python scripts/load_natural_earth.py

Environment variables (.env):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
"""

import os
import zipfile
import requests
import geopandas as gpd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Natural Earth
NE_URL  = "https://naciscdn.org/naturalearth/packages/natural_earth_vector.gpkg.zip"
NE_ZIP  = "data/natural_earth_vector.gpkg.zip"
NE_GPKG = "data/natural_earth_vector.gpkg"

# World Bank Official Boundaries — downloaded automatically
WB_ADMIN1_URL = "https://datacatalogfiles.worldbank.org/ddh-published/0038272/5/DR0095370/World%20Bank%20Official%20Boundaries%20(GeoPackage)/World%20Bank%20Official%20Boundaries%20-%20Admin%201.gpkg"
WB_ADMIN2_URL = "https://datacatalogfiles.worldbank.org/ddh-published/0038272/5/DR0095370/World%20Bank%20Official%20Boundaries%20(GeoPackage)/World%20Bank%20Official%20Boundaries%20-%20Admin%202.gpkg"
WB_ADMIN1 = "data/wb_admin1.gpkg"
WB_ADMIN2 = "data/wb_admin2.gpkg"

# Geofabrik — OSM Bulgaria
GFB_URL       = "https://download.geofabrik.de/europe/bulgaria-latest-free.shp.zip"
GFB_ZIP       = "data/bulgaria-latest-free.shp.zip"
GFB_DIR       = "data/bulgaria-latest-free.shp"
BUILDINGS_SHP = "gis_osm_buildings_a_free_1.shp"
POIS_SHP      = "gis_osm_pois_a_free_1.shp"

# Database
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = os.getenv("DB_PORT", "5433")
DB_NAME     = os.getenv("DB_NAME", "geo_services")
DB_USER     = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_SCHEMA   = "geo"

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ---------------------------------------------------------------------------
# Natural Earth layer definitions
# ---------------------------------------------------------------------------

NE_LAYERS = {

    "ne_10m_admin_0_countries": {
        "table": "countries",
        "if_exists": "replace",
        "columns": [
            "NAME", "FORMAL_EN", "POP_EST", "POP_YEAR", "ECONOMY",
            "INCOME_GRP", "ADM0_ISO", "CONTINENT", "REGION_WB",
            "TYPE", "SOVEREIGNT", "geometry"
        ],
        "rename": {
            "NAME":       "name",
            "FORMAL_EN":  "formal_name",
            "POP_EST":    "pop_est",
            "POP_YEAR":   "pop_year",
            "ECONOMY":    "economy",
            "INCOME_GRP": "income_group",
            "ADM0_ISO":   "code",
            "CONTINENT":  "continent",
            "REGION_WB":  "region_wb",
            "TYPE":       "type",
            "SOVEREIGNT": "sovereignt",
        },
    },

    "ne_10m_populated_places": {
        "table": "places",
        "if_exists": "replace",
        "columns": [
            "NAME", "NAMEASCII", "ADM0_A3", "ADM0NAME", "ADM1NAME",
            "ADM0CAP", "FEATURECLA", "POP_MAX", "LATITUDE", "LONGITUDE",
            "TIMEZONE", "MEGACITY", "WORLDCITY", "geometry"
        ],
        "rename": {
            "NAME":       "name",
            "NAMEASCII":  "name_ascii",
            "ADM0_A3":    "country_code",
            "ADM0NAME":   "country_name",
            "ADM1NAME":   "admin1_name",
            "ADM0CAP":    "is_capital",
            "FEATURECLA": "type",
            "POP_MAX":    "population",
            "LATITUDE":   "lat",
            "LONGITUDE":  "lon",
            "TIMEZONE":   "timezone",
            "MEGACITY":   "is_megacity",
            "WORLDCITY":  "is_world_city",
        },
    },

    "ne_10m_railroads": {
        "table": "railroads",
        "if_exists": "replace",
        "columns": [
            "rwdb_rr_id", "category", "continent",
            "electric", "featurecla", "mult_track", "geometry"
        ],
        "rename": {
            "rwdb_rr_id": "code",
            "featurecla": "type",
            "mult_track": "multi_track",
        },
    },

    "ne_10m_roads": {
        "table": "roads",
        "if_exists": "replace",
        "columns": [
            "continent", "expressway", "featurecla", "length_km",
            "level", "localtype", "sov_a3", "toll", "type", "geometry"
        ],
        "rename": {
            "featurecla": "feature_class",
            "sov_a3":     "country_code",
            "localtype":  "local_type",
        },
    },

    "ne_10m_rivers_lake_centerlines": {
        "table": "rivers",
        "if_exists": "replace",
        "columns": [
            "featurecla", "name", "name_en", "geometry"
        ],
        "rename": {
            "featurecla": "type",
        },
    },
}

# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def download_file(url: str, dest_path: str, label: str):
    """Download a file with progress indicator. Skips if already exists."""
    if os.path.exists(dest_path):
        print(f"  '{dest_path}' already exists, skipping download.")
        return
    print(f"  Downloading {label}...")
    response = requests.get(url, stream=True)
    response.raise_for_status()
    total = int(response.headers.get("content-length", 0))
    downloaded = 0
    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                print(f"    {downloaded / total * 100:.1f}%", end="\r")
    print()
    print(f"  Download complete: {dest_path}")


def download_wb_boundaries():
    """Download World Bank Official Boundaries GeoPackages."""
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(WB_ADMIN1):
        download_file(WB_ADMIN1_URL, WB_ADMIN1, "World Bank Admin 1 boundaries")
    else:
        print(f"  '{WB_ADMIN1}' already exists, skipping.")
    if not os.path.exists(WB_ADMIN2):
        download_file(WB_ADMIN2_URL, WB_ADMIN2, "World Bank Admin 2 boundaries")
    else:
        print(f"  '{WB_ADMIN2}' already exists, skipping.")


def download_natural_earth():
    """Download and extract the Natural Earth GeoPackage."""
    os.makedirs("data", exist_ok=True)
    if os.path.exists(NE_GPKG):
        print(f"  GeoPackage already exists at '{NE_GPKG}', skipping.")
        return
    download_file(NE_URL, NE_ZIP, "Natural Earth GeoPackage (~500MB)")
    print(f"  Extracting '{NE_ZIP}'...")
    with zipfile.ZipFile(NE_ZIP, "r") as z:
        gpkg_files = [f for f in z.namelist() if f.endswith(".gpkg")]
        if not gpkg_files:
            raise FileNotFoundError("No .gpkg file found in zip archive.")
        z.extract(gpkg_files[0], ".")
        if gpkg_files[0] != NE_GPKG:
            os.rename(gpkg_files[0], NE_GPKG)
    print(f"  Extracted to '{NE_GPKG}'.")


def download_bulgaria_data():
    """Download and extract Geofabrik Bulgaria OSM shapefiles."""
    os.makedirs("data", exist_ok=True)
    buildings_path = os.path.join(GFB_DIR, BUILDINGS_SHP)
    pois_path      = os.path.join(GFB_DIR, POIS_SHP)

    if os.path.exists(buildings_path) and os.path.exists(pois_path):
        print(f"  Bulgaria shapefiles already exist in '{GFB_DIR}/', skipping.")
        return

    download_file(GFB_URL, GFB_ZIP, "Geofabrik Bulgaria OSM (~50MB)")
    print(f"  Extracting Bulgaria shapefiles from '{GFB_ZIP}'...")
    os.makedirs(GFB_DIR, exist_ok=True)
    with zipfile.ZipFile(GFB_ZIP, "r") as z:
        shp_bases = [
            BUILDINGS_SHP.replace(".shp", ""),
            POIS_SHP.replace(".shp", ""),
        ]
        target_files = [
            f for f in z.namelist()
            if any(os.path.basename(f).startswith(base) for base in shp_bases)
        ]
        if not target_files:
            raise FileNotFoundError("Required shapefiles not found in zip.")
        for f in target_files:
            z.extract(f, GFB_DIR)
            extracted = os.path.join(GFB_DIR, f)
            target    = os.path.join(GFB_DIR, os.path.basename(f))
            if extracted != target and os.path.exists(extracted):
                os.rename(extracted, target)
    print(f"  Extracted Bulgaria shapefiles to '{GFB_DIR}/'.")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_engine():
    return create_engine(DATABASE_URL)


def ensure_postgis(engine):
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {DB_SCHEMA};"))
        conn.commit()
    print(f"  PostGIS extension and '{DB_SCHEMA}' schema verified.")


def write_to_postgis(gdf, table: str, if_exists: str, engine):
    """Reproject to EPSG:4326 if needed and write GeoDataFrame to PostGIS."""
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    elif gdf.crs.to_epsg() != 4326:
        print(f"    Reprojecting from EPSG:{gdf.crs.to_epsg()} to EPSG:4326...")
        gdf = gdf.to_crs(epsg=4326)
    print(f"    Writing {len(gdf)} features → geo.{table} (if_exists='{if_exists}')...")
    gdf.to_postgis(
        name=table,
        schema=DB_SCHEMA,
        con=engine,
        if_exists=if_exists,
        index=False,
        chunksize=500,
    )
    print(f"    Done — {len(gdf)} rows loaded into 'geo.{table}'.")


# ---------------------------------------------------------------------------
# Layer loaders
# ---------------------------------------------------------------------------

def load_natural_earth_layer(layer_name: str, config: dict, engine):
    """Read one layer from the Natural Earth GeoPackage and load to PostGIS."""
    print(f"\n  Reading '{layer_name}'...")
    gdf = gpd.read_file(NE_GPKG, layer=layer_name)

    desired  = config["columns"]
    existing = [c for c in desired if c in gdf.columns or c == "geometry"]
    missing  = [c for c in desired if c not in gdf.columns and c != "geometry"]
    if missing:
        print(f"    Warning — columns not found, skipped: {missing}")

    gdf = gdf[existing].copy()

    if "rename" in config:
        gdf = gdf.rename(columns=config["rename"])

    if "extra_columns" in config:
        for col, val in config["extra_columns"].items():
            gdf[col] = val

    write_to_postgis(gdf, config["table"], config.get("if_exists", "replace"), engine)


def load_wb_provinces(engine):
    """
    Load World Bank Official Boundaries Admin 1 into geo.provinces.

    Source: World Bank Data Catalog — Official Boundaries GeoPackage
    File:   data/wb_admin1.gpkg

    Columns used:
        ISO_A3    → country_code   Parent country ISO alpha-3
        WB_A3     → wb_code        World Bank country code
        WB_REGION → region_wb      World Bank region
        WB_STATUS → status         WB membership status
        NAM_0     → country_name   Country name
        NAM_1     → name           Province/region name
        ADM1CD_c  → code           Admin 1 code
    """
    if not os.path.exists(WB_ADMIN1):
        print(f"  ERROR: '{WB_ADMIN1}' not found. Run download_wb_boundaries() first.")
        return

    print(f"\n  Reading World Bank Admin 1 from '{WB_ADMIN1}'...")
    gdf = gpd.read_file(WB_ADMIN1)

    keep = ["ISO_A3", "WB_A3", "WB_REGION", "WB_STATUS",
            "NAM_0", "NAM_1", "ADM1CD_c", "geometry"]
    existing = [c for c in keep if c in gdf.columns or c == "geometry"]
    gdf = gdf[existing].copy()

    gdf = gdf.rename(columns={
        "ISO_A3":   "country_code",
        "WB_A3":    "wb_code",
        "WB_REGION":"region_wb",
        "WB_STATUS":"status",
        "NAM_0":    "country_name",
        "NAM_1":    "name",
        "ADM1CD_c": "code",
    })

    # Drop rows with no geometry or no code
    gdf = gdf[gdf.geometry.notna()]
    gdf = gdf[gdf["code"].notna()]

    write_to_postgis(gdf, "provinces", "replace", engine)


def load_wb_municipalities(engine):
    """
    Load World Bank Official Boundaries Admin 2 into geo.municipalities.

    Source: World Bank Data Catalog — Official Boundaries GeoPackage
    File:   data/wb_admin2.gpkg

    Columns used:
        ISO_A3    → country_code   Parent country ISO alpha-3
        WB_A3     → wb_code        World Bank country code
        WB_REGION → region_wb      World Bank region
        WB_STATUS → status         WB membership status
        NAM_0     → country_name   Country name
        NAM_1     → adm1_name      Admin 1 name
        NAM_2     → name           Municipality name
        ADM1CD_c  → adm1_code      Admin 1 code (parent province)
        ADM2CD_c  → code           Admin 2 code (municipality)
    """
    if not os.path.exists(WB_ADMIN2):
        print(f"  ERROR: '{WB_ADMIN2}' not found. Run download_wb_boundaries() first.")
        return

    print(f"\n  Reading World Bank Admin 2 from '{WB_ADMIN2}'...")
    gdf = gpd.read_file(WB_ADMIN2)

    keep = ["ISO_A3", "WB_A3", "WB_REGION", "WB_STATUS",
            "NAM_0", "NAM_1", "NAM_2", "ADM1CD_c", "ADM2CD_c", "geometry"]
    existing = [c for c in keep if c in gdf.columns or c == "geometry"]
    gdf = gdf[existing].copy()

    gdf = gdf.rename(columns={
        "ISO_A3":   "country_code",
        "WB_A3":    "wb_code",
        "WB_REGION":"region_wb",
        "WB_STATUS":"status",
        "NAM_0":    "country_name",
        "NAM_1":    "adm1_name",
        "NAM_2":    "name",
        "ADM1CD_c": "adm1_code",
        "ADM2CD_c": "code",
    })

    # Drop rows with no geometry or no code
    gdf = gdf[gdf.geometry.notna()]
    gdf = gdf[gdf["code"].notna()]

    write_to_postgis(gdf, "municipalities", "replace", engine)


def load_bulgaria_buildings(engine):
    """Load OSM Bulgaria building footprints into geo.buildings."""
    path = os.path.join(GFB_DIR, BUILDINGS_SHP)
    print(f"\n  Reading Bulgaria buildings from '{path}'...")
    gdf  = gpd.read_file(path)
    keep = [c for c in ["name", "type", "geometry"] if c in gdf.columns]
    gdf  = gdf[keep].copy()
    gdf["country_code"] = "BGR"
    write_to_postgis(gdf, "buildings", "replace", engine)


def load_bulgaria_pois(engine):
    """Load OSM Bulgaria points of interest into geo.pois."""
    path = os.path.join(GFB_DIR, POIS_SHP)
    print(f"\n  Reading Bulgaria POIs from '{path}'...")
    gdf  = gpd.read_file(path)
    keep = [c for c in ["name", "fclass", "geometry"] if c in gdf.columns]
    gdf  = gdf[keep].copy()
    gdf  = gdf.rename(columns={"fclass": "type"})
    gdf["country_code"] = "BGR"
    write_to_postgis(gdf, "pois", "replace", engine)


def create_spatial_indexes(engine):
    """Create GIST indexes on all geometry columns."""
    tables = [
        "countries", "provinces", "municipalities",
        "roads", "rivers", "railroads",
        "places", "buildings", "pois"
    ]
    print()
    with engine.connect() as conn:
        for table in tables:
            # Check table exists before indexing
            exists = conn.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = :table"
            ), {"schema": DB_SCHEMA, "table": table}).fetchone()
            if not exists:
                print(f"  Skipping spatial index on {table} — table not found.")
                continue
            idx = f"idx_{table}_geom"
            conn.execute(text(
                f"CREATE INDEX IF NOT EXISTS {idx} "
                f"ON {DB_SCHEMA}.{table} USING GIST(geometry);"
            ))
            print(f"  Spatial index created: {idx}")
        conn.commit()


def create_attribute_indexes(engine):
    """Create B-tree indexes on commonly filtered columns.
    Skips silently if the column does not exist in the table.
    """
    indexes = [
        ("countries",      "code"),
        ("countries",      "continent"),
        ("countries",      "region_wb"),
        ("provinces",      "code"),
        ("provinces",      "country_code"),
        ("provinces",      "region_wb"),
        ("municipalities", "code"),
        ("municipalities", "country_code"),
        ("municipalities", "adm1_code"),
        ("places",         "country_code"),
        ("places",         "population"),
        ("roads",          "country_code"),
        ("roads",          "type"),
        ("roads",          "level"),
        ("railroads",      "continent"),
        ("buildings",      "type"),
        ("buildings",      "country_code"),
        ("pois",           "type"),
        ("pois",           "country_code"),
    ]
    with engine.connect() as conn:
        for table, col in indexes:
            exists = conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = :schema "
                "AND table_name = :table "
                "AND column_name = :col"
            ), {"schema": DB_SCHEMA, "table": table, "col": col}).fetchone()
            if not exists:
                print(f"  Skipping index on {table}.{col} — column not found.")
                continue
            idx = f"idx_{table}_{col}"
            conn.execute(text(
                f"CREATE INDEX IF NOT EXISTS {idx} "
                f"ON {DB_SCHEMA}.{table}({col});"
            ))
            print(f"  Attribute index created: {idx}")
        conn.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Geo Services Data Loader")
    print("=" * 60)

    print("\n[1/7] Downloading datasets...")
    download_wb_boundaries()
    download_natural_earth()
    download_bulgaria_data()

    print("\n[2/7] Connecting to PostGIS...")
    engine = get_engine()
    ensure_postgis(engine)
    print(f"  Connected: {DB_HOST}:{DB_PORT}/{DB_NAME}")

    print("\n[3/7] Loading Natural Earth layers (countries, roads, rivers, railroads, places)...")
    for layer_name, config in NE_LAYERS.items():
        try:
            load_natural_earth_layer(layer_name, config, engine)
        except Exception as e:
            print(f"  ERROR loading '{layer_name}': {e}")

    print("\n[4/7] Loading World Bank Official Boundaries — Admin 1 provinces...")
    try:
        load_wb_provinces(engine)
    except Exception as e:
        print(f"  ERROR loading WB provinces: {e}")

    print("\n[5/7] Loading World Bank Official Boundaries — Admin 2 municipalities...")
    try:
        load_wb_municipalities(engine)
    except Exception as e:
        print(f"  ERROR loading WB municipalities: {e}")

    print("\n[6/7] Loading Bulgaria buildings (OSM via Geofabrik)...")
    try:
        load_bulgaria_buildings(engine)
    except Exception as e:
        print(f"  ERROR loading Bulgaria buildings: {e}")

    print("\n[7/7] Loading Bulgaria POIs (OSM via Geofabrik)...")
    try:
        load_bulgaria_pois(engine)
    except Exception as e:
        print(f"  ERROR loading Bulgaria POIs: {e}")


    print("\nCreating spatial indexes...")
    create_spatial_indexes(engine)

    print("\nCreating attribute indexes...")
    create_attribute_indexes(engine)

    print("\n" + "=" * 60)
    print("  Database ready.")
    print("  Tables loaded:")
    print("    geo.countries      — Natural Earth Admin 0")
    print("    geo.provinces      — World Bank Official Boundaries Admin 1")
    print("    geo.municipalities — World Bank Official Boundaries Admin 2")
    print("    geo.roads          — Natural Earth 10m")
    print("    geo.rivers         — Natural Earth 10m")
    print("    geo.railroads      — Natural Earth 10m")
    print("    geo.places         — Natural Earth 10m")
    print("    geo.buildings      — OSM Bulgaria (Geofabrik)")
    print("    geo.pois           — OSM Bulgaria (Geofabrik)")
    print("=" * 60)


if __name__ == "__main__":
    main()
