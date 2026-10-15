import os

# ---------------------------------------------------------------------------
# Framework configuration.
#
# Every deployment-specific value is read from an environment variable with a
# safe local default, so a fresh clone runs out of the box and real projects
# only need to export env vars (or use a .env file they manage themselves).
#
# Usage in modules:  from slapz102_core import config  ->  config.mainDB
# ---------------------------------------------------------------------------

# Flask session signing secret. ALWAYS override in production:
#   export FLASK_SECRET_KEY="$(python3 -c 'import os; print(os.urandom(24))')"
G_FLASK_SECRET = os.environ.get("FLASK_SECRET_KEY", "dev-only-unsafe-secret")

G_HOME_PATH = os.getcwd()
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

# Timestamp offset (in hours) applied to rec_timestamp fields by the core.
JKTA_TZ = 7
