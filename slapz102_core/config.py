import os

# ---------------------------------------------------------------------------
# Framework configuration — LOCAL FILE, NOT COMMITTED TO GIT.
#
# Each project keeps its own copy:  cp slapz102_core/config_sample.py slapz102_core/config.py
# config.py is listed in .gitignore so unique values (secret key, DB name,
# public URL) never reach the repository.
#
# Usage in modules:  from slapz102_core import config  ->  config.mainDB
# ---------------------------------------------------------------------------

# Flask session signing secret — unique per project, keep it private:
#   python3 -c "import os; print(os.urandom(24).hex())"
G_FLASK_SECRET = os.environ.get("FLASK_SECRET_KEY", "603ac68715041cd04bb9661ef0ad8ed23f172bfceb642a47")

# Repo root, independent of the folder the server is launched from
G_HOME_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G_STATIC_URL_PATH = "/static"
G_UPLOAD_PATH = G_HOME_PATH + G_STATIC_URL_PATH + "/upload"
G_UPLOAD_URL_PATH = G_STATIC_URL_PATH + "/upload"

# Public URL of the deployed site (no trailing slash). Used to build absolute
# URLs for Open Graph / share previews.
G_PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", "http://localhost:5004").strip().rstrip("/")

# Display name used by the sample module's templates
G_SITE_NAME = os.environ.get("SITE_NAME", "SLAPZ Boilerplate")

# Default social-share / Open Graph image (relative to /static)
G_OG_IMAGE_PATH = G_STATIC_URL_PATH + "/brand/og-default.jpg"

# DATABASE ---------------------------------------------------------------
# MongoDB connection. Override MONGO_URI / MONGO_DB_NAME per environment.
mainDB = os.environ.get("MONGO_DB_NAME", "slapz")
mainDB_string = os.environ.get(
    "MONGO_URI", "mongodb://127.0.0.1:27017/"
).rstrip("/") + "/" + mainDB

G_DATABASE_CONNECT = [
    {"dbname": mainDB, "dbstring": mainDB_string}
]

# Offset in hours added to UTC when building rec_timestamp fields
JKTA_TZ = int(os.environ.get("TZ_OFFSET_HOURS", "7"))
