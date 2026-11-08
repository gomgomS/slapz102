# MongoDB Patterns (SLAPZ / slapz102, PyMongo 4)

## Contents
- Framework rules
- The 4-step query style
- Creating records
- Updating and soft deleting
- Indexes (where and how)
- Performance rules
- Slow vs fast cheat sheet
- Checking a query with explain()
- Forbidden

---

## Framework rules

1. Schema-first: add the collection to the `db` dict in `slapz102_core/model.py` with an empty default per field. Name starts with `db_`. Do NOT declare `pkey`, `ipkey`, `rec_timestamp`, `rec_timestamp_str`, `is_deleted`.
2. Additions only: never drop/rename collections or remove fields from `model.py`.
3. Every read filters `"is_deleted": False`. Delete = `$set` `is_deleted: True`.
4. Templates get documents projected with `"_id": 0`.
5. Use PyMongo 4 methods only: `find`, `find_one`, `insert_one`, `update_one`, `update_many`, `bulk_write`, `find_one_and_update`, `count_documents`, `aggregate`, `create_index`.

Framework-managed fields you can rely on:

| Field | Meaning |
|---|---|
| `pkey` | unique string id (`<ObjectId>-<rand>-<counter>-<ms>`) |
| `ipkey` | string of the ObjectId |
| `rec_timestamp` | creation time in ms (local offset `config.JKTA_TZ`), best field for "newest first" |
| `rec_timestamp_str` | `"YYYY-MM-DD HH:MM:SS"` for display |
| `is_deleted` | soft-delete flag |

## The 4-step query style

Write every query as four named steps. It reads like a sentence and keeps
every performance knob visible:

```python
# 1. WHAT - which documents
query = {}
query["is_deleted"] = False
query["status"] = "PUBLISHED"

# 2. WHICH FIELDS - only what the caller shows
projection = {}
projection["_id"] = 0
projection["slug"] = 1
projection["title"] = 1
projection["rec_timestamp_str"] = 1

# 3. HOW - order + size
cursor = self.mgdDB.db_article.find(query, projection)
cursor = cursor.sort("rec_timestamp", -1)
cursor = cursor.limit(20)

# 4. RUN
recs = list(cursor)
```

Rules for each step:

1. **WHAT**: build the dict key by key. Add optional filters with `if value != "":`. Equality filters first, ranges last (`{"$gte": ...}`).
2. **WHICH FIELDS**: always set `"_id": 0`, then include only the fields the page/API uses (`1`), for lists AND detail pages. Never project sensitive fields (`password`, tokens) outside auth logic. Full rules: `references/mongodb-performance.md`.
3. **HOW**: the sort field must be in the index right after the equality fields. Always `limit()` a list. Multi-field sort: `cursor.sort([("status", 1), ("rec_timestamp", -1)])`.
4. **RUN**: `list(cursor)` for bounded results; `find_one(query, projection)` for one document. Iterate the cursor directly (no `list()`) only for large exports.

Short lookups may stay inline, like `sample_proc.get_item`, but still with an explicit projection:

```python
rec = self.mgdDB.db_article.find_one(
    {"slug": slug, "is_deleted": False},
    {"_id": 0, "slug": 1, "title": 1, "body": 1, "rec_timestamp_str": 1}
)
```

## Creating records

Always through the model (it adds `pkey`, timestamps, `is_deleted`):

```python
rec = database.new(self.mgdDB, "db_article")
rec.put("slug", slug)
rec.put("title", title)
rec.insert()
```

- `rec.put()` with an unknown key raises `ValueError` on purpose: add the field to `model.py` first.
- Never `insert_one` a raw dict into a feature collection, and never use `upsert=True` to create feature records (it skips the framework fields).
- Many records at once: build each with `database.new(...)` and `insert()` them. This is fine for normal forms; for big imports, ask before adding a batch helper.

## Updating and soft deleting

```python
query = {}
query["slug"] = slug
query["is_deleted"] = False

changes = {}
changes["title"] = title
changes["status"] = status

result = self.mgdDB.db_article.update_one(query, {"$set": changes})
if result.matched_count == 0:
    return {"status": "ERROR", "desc": "Article not found"}
# end if
```

- `$set` only the changed fields. Never replace the whole document.
- `matched_count` tells you "not found" without an extra read.
- Counters: `{"$inc": {"view_count": 1}}` (atomic, no race).
- Soft delete: `update_one(query, {"$set": {"is_deleted": True}})`.
- Same change on many docs: `update_many(query, {"$set": changes})`.
- Different changes on many docs: `bulk_write([UpdateOne(...), ...], ordered=False)` (`from pymongo import UpdateOne`).
- Claim or take something exactly once: `find_one_and_update(query, update, return_document=pymongo.ReturnDocument.AFTER)`.

## Indexes (where and how)

The framework has no migration tool, so each proc creates its own indexes
once per process. `create_index` is idempotent, and the class flag avoids a
round trip on every request:

```python
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
        # detail page: find_one by slug
        self.mgdDB.db_article.create_index([("slug", 1), ("is_deleted", 1)])
        # list page: is_deleted + status, newest first
        self.mgdDB.db_article.create_index([("is_deleted", 1), ("status", 1), ("rec_timestamp", -1)])
    # end def
# end class
```

How to design an index: **E-S-R** = Equality fields, then Sort field, then Range fields.

| Query | Index |
|---|---|
| `{"slug": x, "is_deleted": False}` | `[("slug", 1), ("is_deleted", 1)]` |
| `{"is_deleted": False, "status": s}` sort `rec_timestamp -1` | `[("is_deleted", 1), ("status", 1), ("rec_timestamp", -1)]` |
| `{"is_deleted": False, "fk_user_id": u}` sort `rec_timestamp -1` | `[("is_deleted", 1), ("fk_user_id", 1), ("rec_timestamp", -1)]` |
| `{"is_deleted": False, "status": s, "rec_timestamp": {"$gte": t}}` sort `rec_timestamp -1` | `[("is_deleted", 1), ("status", 1), ("rec_timestamp", -1)]` |

- Unique among live records: `create_index([("slug", 1)], unique=True, partialFilterExpression={"is_deleted": False})`.
- One index per query shape that runs on a page/API. Don't index every field: each index slows writes.
- A compound index also serves its prefixes (`(a, b, c)` serves `a` and `a, b`), so don't add those separately.
- Never drop an existing index from code.

## Performance rules

1. **Index every list/lookup query** (E-S-R above). An un-indexed query on a big collection is a full scan.
2. **Project** only needed fields. Smaller documents mean less network and memory.
3. **Always limit** lists. Cap user page size (for example `max 50`).
4. **Pagination**:
   - Normal pages: `skip((page - 1) * size).limit(size)`. Fine for the first few hundred pages.
   - Infinite scroll / huge collections: range pagination with `rec_timestamp < last_seen` + `limit`. Cost stays flat regardless of depth.
5. **Count** with `count_documents(query)` using the same indexed `query`. Never `len(list(find()))`.
6. **No query inside a loop**: collect ids, one `find({"x": {"$in": ids}})`, build a dict, then map.
7. **Exists check**: `find_one(query, {"_id": 1})` returns a tiny document.
8. **Search**: prefer an anchored, escaped, case-sensitive prefix `{"$regex": "^" + re.escape(keyword)}` (can use an index). Unanchored or `$options: "i"` regex scans everything; only use it on small collections or with a strong extra filter plus a limit.
9. **Aggregation order**: `$match` first (uses indexes), then `$sort`, `$limit`, then `$project` / `$group` / `$lookup`. `$lookup` only on an indexed `foreignField`.
10. **Whitelist user-controlled sort fields** through a dict, so users can't sort by un-indexed fields.
11. **Atomic writes** (`$set`, `$inc`, `find_one_and_update`) instead of read-modify-write.

## Slow vs fast cheat sheet

| Slow | Fast |
|---|---|
| `find({})` then filter in Python | put the filter in `query` |
| `find(query)` with no projection on a list page | `find(query, projection)` with only shown fields |
| `list(find(query))` with no limit | `.limit(size)` |
| `len(list(find(query)))` | `count_documents(query)` |
| `find_one` per item in a `for` loop | one `find` with `$in` + dict lookup |
| `find_one` then `update_one` | `update_one` + `matched_count` |
| read counter, `+1`, write back | `$inc` |
| `update_one` in a loop | `update_many` or `bulk_write` |
| `{"$regex": keyword, "$options": "i"}` | `{"$regex": "^" + re.escape(keyword)}` |
| `$group` / `$project` before `$match` | `$match` first |
| `skip(100000)` | range pagination on `rec_timestamp` |

## Checking a query with explain()

During development only (never in committed code):

```python
plan = self.mgdDB.db_article.find(query, projection).sort("rec_timestamp", -1).limit(20).explain()
print(plan["queryPlanner"]["winningPlan"])
```

Look for `IXSCAN` (good). `COLLSCAN` means no index is used; `SORT` stage
means the sort is in memory: fix the index order (E-S-R).

## Forbidden

- `remove()`, `update()`, `insert()`, `count()` on collections (removed in PyMongo 4).
- `delete_one` / `delete_many` on feature data (soft delete only).
- `drop()`, `rename()`, `drop_index()` from module code.
- Raw `insert_one` of feature records (use `database.new`).
- f-strings or `$where` / JavaScript in queries.
