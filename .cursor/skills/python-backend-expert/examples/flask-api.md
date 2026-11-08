# Example: a complete feature module (`article`)

A full feature built the SLAPZ way: HTML pages + a JSON API, paginated list,
detail, create, update, soft delete, indexes, and tests. Copy and rename.

Files:

```
slapz102_core/model.py                              + "db_article" schema
slapz102_modules/article/article_proc.py            business logic + DB
slapz102_modules/article/article_blueprint.py       routes
slapz102_modules/view/article/view_article.py       request/response glue
templates/article.html                              list page
templates/article_item.html                         detail page
server.py                                           + 2 lines
tests/test_article.py                               tests
```

---

## 1. `slapz102_core/model.py` (add inside `db`)

```python
    "db_article": {
        "fk_user_id": "",
        "slug": "",
        "title": "",
        "body": "",
        "status": "PUBLISHED",
        "view_count": 0
    }
```

## 2. `slapz102_modules/article/article_proc.py`

```python
import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from slapz102_core import database
from slapz102_core import config

PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 50
ALLOWED_STATUS = ["DRAFT", "PUBLISHED"]

def _slugify(title):
    slug = (title or "").strip().lower()
    cleaned = ""
    for char in slug:
        if char.isalnum() or char in "- ":
            cleaned = cleaned + char
        # end if
    # end for
    slug = "-".join(cleaned.split())
    return slug or "article"
# end def

def _to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
    # end try
# end def

class article_proc:

    mgdDB = database.get_db_conn(config.mainDB)
    indexes_ready = False

    def __init__(self, app=None):
        self.webapp = app
        if not article_proc.indexes_ready:
            self._ensure_indexes()
            article_proc.indexes_ready = True
        # end if
    # end def

    def _ensure_indexes(self):
        self.mgdDB.db_article.create_index([("slug", 1), ("is_deleted", 1)])
        self.mgdDB.db_article.create_index([("is_deleted", 1), ("status", 1), ("rec_timestamp", -1)])
    # end def

    def list_articles(self, page, page_size):
        page = _to_int(page, 1)
        if page < 1:
            page = 1
        # end if
        page_size = _to_int(page_size, PAGE_SIZE_DEFAULT)
        if page_size < 1 or page_size > PAGE_SIZE_MAX:
            page_size = PAGE_SIZE_DEFAULT
        # end if

        query = {}
        query["is_deleted"] = False
        query["status"] = "PUBLISHED"

        projection = {}
        projection["_id"] = 0
        projection["slug"] = 1
        projection["title"] = 1
        projection["rec_timestamp_str"] = 1

        cursor = self.mgdDB.db_article.find(query, projection)
        cursor = cursor.sort("rec_timestamp", -1)
        cursor = cursor.skip((page - 1) * page_size)
        cursor = cursor.limit(page_size)
        items = list(cursor)

        total = self.mgdDB.db_article.count_documents(query)

        result = {}
        result["items"] = items
        result["page"] = page
        result["page_size"] = page_size
        result["total"] = total
        result["has_next"] = page * page_size < total
        return result
    # end def

    def get_article(self, slug):
        query = {}
        query["slug"] = slug
        query["is_deleted"] = False

        projection = {}
        projection["_id"] = 0
        projection["slug"] = 1
        projection["title"] = 1
        projection["body"] = 1
        projection["view_count"] = 1
        projection["rec_timestamp_str"] = 1

        rec = self.mgdDB.db_article.find_one(query, projection)
        return rec
    # end def

    def _slug_taken(self, slug):
        rec = self.mgdDB.db_article.find_one(
            {"slug": slug, "is_deleted": False},
            {"_id": 1}
        )
        return rec != None
    # end def

    def _unique_slug(self, slug):
        candidate = slug
        seq = 2
        while self._slug_taken(candidate):
            candidate = slug + "-" + str(seq)
            seq = seq + 1
        # end while
        return candidate
    # end def

    def create_article(self, params):
        title = (params.get("title") or "").strip()
        body = (params.get("body") or "").strip()
        status = (params.get("status") or "PUBLISHED").strip().upper()

        if title == "":
            return {"status": "ERROR", "desc": "Title is required"}
        # end if
        if status not in ALLOWED_STATUS:
            return {"status": "ERROR", "desc": "Invalid status"}
        # end if

        slug = self._unique_slug(_slugify(title))
        rec = database.new(self.mgdDB, "db_article")
        rec.put("slug", slug)
        rec.put("title", title)
        rec.put("body", body)
        rec.put("status", status)
        rec.insert()
        return {"status": "SUCCESS", "desc": "Article created", "data": {"slug": slug}}
    # end def

    def update_article(self, slug, params):
        title = (params.get("title") or "").strip()
        body = (params.get("body") or "").strip()

        if title == "":
            return {"status": "ERROR", "desc": "Title is required"}
        # end if

        query = {}
        query["slug"] = slug
        query["is_deleted"] = False

        changes = {}
        changes["title"] = title
        changes["body"] = body

        result = self.mgdDB.db_article.update_one(query, {"$set": changes})
        if result.matched_count == 0:
            return {"status": "ERROR", "desc": "Article not found"}
        # end if
        return {"status": "SUCCESS", "desc": "Article updated"}
    # end def

    def add_view(self, slug):
        self.mgdDB.db_article.update_one(
            {"slug": slug, "is_deleted": False},
            {"$inc": {"view_count": 1}}
        )
    # end def

    def delete_article(self, slug):
        result = self.mgdDB.db_article.update_one(
            {"slug": slug, "is_deleted": False},
            {"$set": {"is_deleted": True}}
        )
        if result.matched_count == 0:
            return {"status": "ERROR", "desc": "Article not found"}
        # end if
        return {"status": "SUCCESS", "desc": "Article deleted"}
    # end def
# end class
```

Why this is fast:
- Both queries match an index (`slug + is_deleted`, `is_deleted + status + rec_timestamp`).
- The list projects 3 fields and is capped at `PAGE_SIZE_MAX`.
- Update/delete/view-count are one atomic call each; `matched_count` replaces a separate read.

## 3. `slapz102_modules/article/article_blueprint.py`

```python
import sys
import traceback

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import Blueprint

from view.article import view_article

article_blueprint = Blueprint("article_blueprint", __name__)

@article_blueprint.route("/article", methods=["GET"])
def index():
    try:
        return view_article.html_index()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@article_blueprint.route("/article/create", methods=["POST"])
def create():
    try:
        return view_article.html_create()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@article_blueprint.route("/article/update/<slug>", methods=["POST"])
def update(slug):
    try:
        return view_article.html_update(slug)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@article_blueprint.route("/article/delete/<slug>", methods=["POST"])
def delete(slug):
    try:
        return view_article.html_delete(slug)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@article_blueprint.route("/article/<slug>", methods=["GET"])
def detail(slug):
    try:
        return view_article.html_item(slug)
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def

@article_blueprint.route("/api/article/list", methods=["GET"])
def api_list():
    try:
        return view_article.api_list()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def
```

## 4. `slapz102_modules/view/article/view_article.py`

```python
import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import render_template, redirect, request, url_for, jsonify
from slapz102_core import config
from slapz102_core import helper
from slapz102_stdlib import csrf
from slapz102_stdlib import sanitize

from article.article_proc import article_proc

def _base_data():
    return {
        "site_name": config.G_SITE_NAME,
        "csrf_token": csrf.get_token(),
        "og_image": config.G_PUBLIC_SITE_URL + config.G_OG_IMAGE_PATH,
        "og_url": config.G_PUBLIC_SITE_URL + "/article"
    }
# end def

def html_index():
    params = sanitize.clean_html_dic(request.args.to_dict())
    proc = article_proc()
    data = _base_data()
    data["result"] = proc.list_articles(params.get("page"), params.get("page_size"))
    data["form_error"] = (params.get("error") or "").strip()
    return render_template("article.html", data=data)
# end def

def html_item(slug):
    proc = article_proc()
    item = proc.get_article(slug)
    if item == None:
        return "Not found", 404
    # end if
    proc.add_view(slug)
    data = _base_data()
    data["item"] = item
    return render_template("article_item.html", data=data)
# end def

def html_create():
    if not csrf.validate():
        return redirect(url_for("article_blueprint.index", error="Invalid session, please try again"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = article_proc()
    result = proc.create_article(params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("article_blueprint.index", error=result.get("desc", "")))
    # end if
    return redirect(url_for("article_blueprint.detail", slug=result["data"]["slug"]))
# end def

def html_update(slug):
    if not csrf.validate():
        return redirect(url_for("article_blueprint.index", error="Invalid session, please try again"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    proc = article_proc()
    result = proc.update_article(slug, params)
    if result.get("status") != "SUCCESS":
        return redirect(url_for("article_blueprint.index", error=result.get("desc", "")))
    # end if
    return redirect(url_for("article_blueprint.detail", slug=slug))
# end def

def html_delete(slug):
    if not csrf.validate():
        return redirect(url_for("article_blueprint.index", error="Invalid session, please try again"))
    # end if
    proc = article_proc()
    proc.delete_article(slug)
    return redirect(url_for("article_blueprint.index"))
# end def

def api_list():
    params = sanitize.clean_html_dic(request.args.to_dict())
    proc = article_proc()
    result = proc.list_articles(params.get("page"), params.get("page_size"))
    msg = helper.response_msg_factory("SUCCESS", "Articles loaded", result)
    return jsonify(msg.get())
# end def
```

## 5. `templates/article.html` (core part)

```html
{% extends "base.html" %}
{% block title %}Articles - {{ data.site_name }}{% endblock %}
{% block content %}
  {% if data.form_error %}<p class="text-danger">{{ data.form_error }}</p>{% endif %}

  <form method="post" action="{{ url_for('article_blueprint.create') }}">
    <input type="hidden" name="csrf_token" value="{{ data.csrf_token }}">
    <input type="text" name="title" required>
    <textarea name="body"></textarea>
    <button type="submit">Create</button>
  </form>

  {% for item in data.result["items"] %}
    <a href="{{ url_for('article_blueprint.detail', slug=item.slug) }}">{{ item.title }}</a>
    <small>{{ item.rec_timestamp_str }}</small>
  {% else %}
    <p>No articles yet</p>
  {% endfor %}

  {% if data.result.page > 1 %}
    <a href="{{ url_for('article_blueprint.index', page=data.result.page - 1) }}">Previous</a>
  {% endif %}
  {% if data.result.has_next %}
    <a href="{{ url_for('article_blueprint.index', page=data.result.page + 1) }}">Next</a>
  {% endif %}
{% endblock %}
```

Use `data.result["items"]` (not `data.result.items`): `.items` resolves to the dict method in Jinja.

## 6. `server.py` (2 lines)

```python
from article.article_blueprint import article_blueprint

app.register_blueprint(article_blueprint, url_prefix="/")
```

## 7. `tests/test_article.py`

```python
import os
import sys

os.environ["MONGO_DB_NAME"] = "slapz_test"

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

import pytest

from slapz102_core import config
from slapz102_core import database
import server

@pytest.fixture()
def client():
    db = database.get_db_conn(config.mainDB)
    db.client.drop_database(config.mainDB)
    server.app.config["TESTING"] = True
    with server.app.test_client() as client:
        yield client
    # end with
# end def

def _get_csrf_token(client):
    html = client.get("/article").data.decode("utf-8")
    marker = 'name="csrf_token" value="'
    start = html.find(marker) + len(marker)
    end = html.find('"', start)
    return html[start:end]
# end def

def test_create_and_list(client):
    token = _get_csrf_token(client)
    res = client.post("/article/create", data={"csrf_token": token, "title": "Hello"})
    assert res.status_code == 302
    res = client.get("/api/article/list")
    body = res.get_json()
    assert body["status"] == "SUCCESS"
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["slug"] == "hello"
# end def

def test_create_requires_csrf_token(client):
    res = client.post("/article/create", data={"title": "No token"})
    assert res.status_code == 302
    res = client.get("/api/article/list")
    assert res.get_json()["data"]["total"] == 0
# end def

def test_soft_delete(client):
    token = _get_csrf_token(client)
    client.post("/article/create", data={"csrf_token": token, "title": "Bye"})
    res = client.post("/article/delete/bye", data={"csrf_token": token})
    assert res.status_code == 302
    assert client.get("/article/bye").status_code == 404
    db = database.get_db_conn(config.mainDB)
    doc = db.db_article.find_one({"slug": "bye"})
    assert doc["is_deleted"] == True
# end def
```

The fixture drops the test DB, but `article_proc.indexes_ready` stays `True`
for the process, so indexes are not recreated during tests. Queries still
work; indexes only matter for speed.
