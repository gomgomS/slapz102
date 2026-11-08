# Flask Guidelines (SLAPZ / slapz102)

## Contents
- Layers and files
- File header
- Blueprint layer
- View layer (HTML, POST, JSON)
- Proc layer: logic style
- Logic performance rules
- Config, templates, CSS
- Tests

---

## Layers and files

```
server.py                                          register blueprints only
slapz102_modules/<feature>/<feature>_blueprint.py  routes only
slapz102_modules/view/<feature>/view_<feature>.py  request -> sanitize -> proc -> render/redirect/json
slapz102_modules/<feature>/<feature>_proc.py       ALL business logic + DB access
templates/<feature>.html                           extends base.html, reads `data`
```

| Layer | Allowed | Forbidden |
|---|---|---|
| `server.py` | import + `app.register_blueprint` | logic, DB |
| Blueprint | route, delegate to view, catch exceptions | DB, `render_template` |
| View | read request, sanitize, CSRF, call proc, render/redirect/jsonify | business rules, DB queries |
| Proc | business rules, DB access | `request` / `session`, routes |

## File header

Every Python file:

```python
import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")
```

Imports after the header: `from slapz102_core import config`,
`from slapz102_stdlib import sanitize`, `from <feature>.<feature>_proc import <feature>_proc`,
`from view.<feature> import view_<feature>`. Never relative imports.

## Blueprint layer

```python
<feature>_blueprint = Blueprint("<feature>_blueprint", __name__)

@<feature>_blueprint.route("/<feature>", methods=["GET"])
def index():
    try:
        return view_<feature>.html_index()
    except Exception as e:
        print(traceback.format_exc())
        return "An error occurred", 500
    # end try
# end def
```

- One route = one view function call. Nothing else.
- Destructive actions (create, update, delete) are `POST` only.
- Register in `server.py`: one import + `app.register_blueprint(<feature>_blueprint, url_prefix="/")`.

## View layer

### GET page

```python
def html_index():
    params = sanitize.clean_html_dic(request.args.to_dict())
    proc = article_proc()
    data = _base_data()
    data["result"] = proc.list_articles(params.get("page"), params.get("page_size"))
    data["form_error"] = (params.get("error") or "").strip()
    return render_template("article.html", data=data)
# end def
```

### POST form

```python
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
    return redirect(url_for("article_blueprint.index"))
# end def
```

- `csrf.validate()` is the FIRST line of every POST view.
- Redirect after POST (no rendering on POST).
- Rich text: `sanitize.clean_rich_html(value)` for that one field, instead of the plain escape.

### JSON response

Use the existing `helper.response_msg_factory` so all APIs share one shape:

```python
from flask import jsonify
from slapz102_core import helper

def api_list():
    params = sanitize.clean_html_dic(request.args.to_dict())
    proc = article_proc()
    result = proc.list_articles(params.get("page"), params.get("page_size"))
    msg = helper.response_msg_factory("SUCCESS", "Articles loaded", result)
    return jsonify(msg.get())
# end def
```

POST APIs that rely on the session cookie still need `csrf.validate()`
(the client sends `csrf_token` as a form field).

### `_base_data()`

Each view module has a `_base_data()` helper (copy from `view_sample.py`) that
returns `site_name`, `csrf_token`, `og_image`, `og_url`. Pass everything to
the template in ONE `data` dict.

## Proc layer: logic style

Shape of every proc class:

```python
class article_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def
# end class
```

Shape of every write method: clean -> guard -> act -> return result.

```python
def update_title(self, slug, params):
    # clean
    title = (params.get("title") or "").strip()

    # guard (early return, one rule per if)
    if title == "":
        return {"status": "ERROR", "desc": "Title is required"}
    # end if
    if len(title) > 200:
        return {"status": "ERROR", "desc": "Title is too long"}
    # end if

    # act (one atomic DB call)
    query = {}
    query["slug"] = slug
    query["is_deleted"] = False

    changes = {}
    changes["title"] = title

    result = self.mgdDB.db_article.update_one(query, {"$set": changes})

    # return
    if result.matched_count == 0:
        return {"status": "ERROR", "desc": "Article not found"}
    # end if
    return {"status": "SUCCESS", "desc": "Article updated"}
# end def
```

Return conventions (match `sample_proc.py` and `helper.response_msg`):

- Write methods -> `{"status": "SUCCESS" | "ERROR", "desc": "..."}`, plus `"data"` when the caller needs something back.
- Read methods -> the record, the list, or `None` when not found.
- Never raise for user mistakes; return an `ERROR` dict. Let real bugs raise so the blueprint logs them.

Helpers live at module level, prefixed with `_`:

```python
def _to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
    # end try
# end def
```

## Logic performance rules

Summary table below; full rules and review checklist in `references/python-performance.md`.

| Do | Instead of |
|---|---|
| One `find` with `$in`, then a dict lookup | a `find_one` inside a `for` loop (N+1) |
| `set()` for "is X in this group" checks | `if x in some_list` inside a loop |
| `dict` keyed by id to join two lists | nested `for` loops |
| `update_one` + check `matched_count` | `find_one` then `update_one` (2 round trips) |
| `$inc` for counters | read value, add 1 in Python, write back (race) |
| `update_many` / `bulk_write` for many rows | `update_one` in a loop |
| `count_documents(query)` | `len(list(find(query)))` |
| `"".join(parts)` when building big strings in a loop | `text = text + part` thousands of times |
| Compute constants once at module level | rebuilding the same list/dict per request |
| One `proc = feature_proc()` per view call | creating a proc per loop iteration |

Additional rules:

- `mgdDB` is a class attribute: the Mongo client and its connection pool are shared. Never create a `MongoClient` in a module.
- Validate and cap anything user-controlled that affects cost: page size, sort field, date range, search length.
- Do not do heavy work at import time beyond what the framework already does.

## Config, templates, CSS

- Settings come from `from slapz102_core import config`. New setting -> env-backed constant in BOTH `config.py` and `config_sample.py`. Never hardcode URLs, secrets, or DB names.
- Templates extend `templates/base.html` (blocks: `title`, `og_title`, `og_description`, `content`). Each POST form includes `<input type="hidden" name="csrf_token" value="{{ data.csrf_token }}">`.
- Tailwind v4: edit `static/v2/input.css`, then `npm run build:css`. Never edit `static/v2/app.output.css`.

## Tests

- Tests live in `tests/`, set `os.environ["MONGO_DB_NAME"] = "slapz_test"` BEFORE importing the framework, and drop that DB in the fixture.
- Get a CSRF token by rendering a page and reading the hidden input (see `tests/test_sample.py`).
- Cover: page renders, POST without token is rejected, valid create, sanitized output, soft delete keeps the document.
- Run `python3 -m pytest tests/ -v`. Everything must pass.
