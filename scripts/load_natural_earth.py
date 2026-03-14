"""
Geo Services Data Loader
========================
Downloads and loads the following datasets into PostGIS:
  1. Natural Earth 10m GeoPackage (global vector layers)
  2. OpenStreetMap Bulgaria buildings via Geofabrik
  3. OpenStreetMap Bulgaria POIs via Geofabrik (hospitals, schools, etc.)

Usage:
    pip install geopandas sqlalchemy psycopg2-binary python-dotenv requests geoalchemy2
    python scripts/load_natural_earth.py

Environment variables (set in .env file):
    DB_HOST      - PostgreSQL host (default: localhost)
    DB_PORT      - PostgreSQL port (default: 5433)
    DB_NAME      - Database name (default: geo_services)
    DB_USER      - PostgreSQL user (default: postgres)
    DB_PASSWORD  - PostgreSQL password
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
NE_ZIP  = "natural_earth_vector.gpkg.zip"
NE_GPKG = "natural_earth_vector.gpkg"

# Geofabrik — OSM Bulgaria
GFB_URL       = "https://download.geofabrik.de/europe/bulgaria-latest-free.shp.zip"
GFB_ZIP       = "bulgaria-latest-free.shp.zip"
GFB_DIR       = "bulgaria-latest-free.shp"
BUILDINGS_SHP = "gis_osm_buildings_a_free_1.shp"
POIS_SHP      = "gis_osm_pois_a_free_1.shp"

# Database
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = os.getenv("DB_PORT", "5433")
DB_NAME     = os.getenv("DB_NAME", "geo_services")
DB_USER     = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "geopassword")
DB_SCHEMA   = "geo"

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ---------------------------------------------------------------------------
# Natural Earth layer definitions
# ---------------------------------------------------------------------------

LAYERS = {

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

    "ne_10m_admin_1_states_provinces": {
        "table": "provinces",
        "if_exists": "replace",
        "columns": [
            "name", "iso_3166_2", "adm0_a3", "type", "type_en",
            "region", "area_sqkm", "latitude", "longitude",
            "geonunit", "geometry"
        ],
        "rename": {
            "iso_3166_2": "code",
            "adm0_a3":    "country_code",
            "type_en":    "type_en",
            "area_sqkm":  "area_sqkm",
            "latitude":   "lat",
            "longitude":  "lon",
            "geonunit":   "geonunit",
        },
    },

    "ne_10m_parks_and_protected_lands_area": {
        "table": "protected_areas",
        "if_exists": "replace",
        "columns": [
            "featurecla", "name", "nps_region", "unit_type", "geometry"
        ],
        "rename": {
            "featurecla": "feature_class",
            "nps_region": "region",
            "unit_type":  "type",
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
# Generic download helper
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


# ---------------------------------------------------------------------------
# Natural Earth download + extract
# ---------------------------------------------------------------------------

def download_natural_earth():
    """Download and extract the Natural Earth GeoPackage."""
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


# ---------------------------------------------------------------------------
# Geofabrik Bulgaria download + extract
# ---------------------------------------------------------------------------

def download_bulgaria_data():
    """Download and extract Geofabrik Bulgaria OSM shapefiles."""
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
            raise FileNotFoundError("Buildings or POIs shapefiles not found in zip.")
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


def load_bulgaria_buildings(engine):
    """Read OSM Bulgaria buildings shapefile and load to PostGIS."""
    path = os.path.join(GFB_DIR, BUILDINGS_SHP)
    print(f"\n  Reading Bulgaria buildings from '{path}'...")
    gdf  = gpd.read_file(path)

    keep    = [c for c in ["name", "type", "geometry"] if c in gdf.columns]
    missing = [c for c in ["name", "type"] if c not in gdf.columns]
    if missing:
        print(f"    Warning — columns not found, skipped: {missing}")

    gdf = gdf[keep].copy()
    gdf["country_code"] = "BGR"

    write_to_postgis(gdf, "buildings", "replace", engine)


def load_bulgaria_pois(engine):
    """Read OSM Bulgaria POIs shapefile and load to PostGIS."""
    path = os.path.join(GFB_DIR, POIS_SHP)
    print(f"\n  Reading Bulgaria POIs from '{path}'...")
    gdf  = gpd.read_file(path)

    keep    = [c for c in ["name", "fclass", "geometry"] if c in gdf.columns]
    missing = [c for c in ["name", "fclass"] if c not in gdf.columns]
    if missing:
        print(f"    Warning — columns not found, skipped: {missing}")

    gdf = gdf[keep].copy()
    gdf = gdf.rename(columns={"fclass": "type"})
    gdf["country_code"] = "BGR"

    write_to_postgis(gdf, "pois", "replace", engine)


# ---------------------------------------------------------------------------
# Index creation
# ---------------------------------------------------------------------------

def create_spatial_indexes(engine):
    """Create GIST indexes on all geometry columns."""
    tables = [
        "countries", "provinces", "roads", "rivers", "railroads",
        "places", "protected_areas", "buildings", "pois"
    ]
    print()
    with engine.connect() as conn:
        for table in tables:
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
        ("countries",  "code"),
        ("countries",  "continent"),
        ("countries",  "region_wb"),
        ("provinces",  "code"),
        ("provinces",  "country_code"),
        ("places",          "country_code"),
        ("places",          "population"),
        ("roads",           "country_code"),
        ("roads",           "type"),
        ("roads",           "level"),
        ("railroads",       "continent"),
        ("protected_areas", "type"),
        ("buildings",       "type"),
        ("buildings",       "country_code"),
        ("pois",            "type"),
        ("pois",            "country_code"),
    ]
    with engine.connect() as conn:
        for table, col in indexes:
            # Check column exists before creating index
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

    print("\n[1/6] Downloading datasets...")
    download_natural_earth()
    download_bulgaria_data()

    print("\n[2/6] Connecting to PostGIS...")
    engine = get_engine()
    ensure_postgis(engine)
    print(f"  Connected: {DB_HOST}:{DB_PORT}/{DB_NAME}")

    print("\n[3/6] Loading Natural Earth layers...")
    for layer_name, config in LAYERS.items():
        try:
            load_natural_earth_layer(layer_name, config, engine)
        except Exception as e:
            print(f"  ERROR loading '{layer_name}': {e}")

    print("\n[4/6] Loading Bulgaria buildings (OSM via Geofabrik)...")
    try:
        load_bulgaria_buildings(engine)
    except Exception as e:
        print(f"  ERROR loading Bulgaria buildings: {e}")

    print("\n[5/6] Loading Bulgaria POIs (OSM via Geofabrik)...")
    try:
        load_bulgaria_pois(engine)
    except Exception as e:
        print(f"  ERROR loading Bulgaria POIs: {e}")

    print("\n[6/6] Creating indexes...")
    create_spatial_indexes(engine)
    create_attribute_indexes(engine)

    print("\n" + "=" * 60)
    print("  Database ready.")
    print("=" * 60)


if __name__ == "__main__":
    main()