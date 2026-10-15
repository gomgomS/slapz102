import os
import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Flask
from slapz102_core import config

app = Flask(__name__)
app.secret_key = config.G_FLASK_SECRET

# Import one blueprint per feature module, then register it below.
# Adding a new feature = create slapz102_modules/<feature>/ with
# <feature>_blueprint.py, then add two matching lines here.
from sample.sample_blueprint import sample_blueprint

app.register_blueprint(sample_blueprint, url_prefix="/")

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5004")),
        debug=True
    )
# end if
