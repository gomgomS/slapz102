# Example: MongoDB queries in the house style

Copy-ready proc methods. Every query uses the same 4 steps:
**1. WHAT** (`query`), **2. WHICH FIELDS** (`projection`), **3. HOW** (sort / skip / limit), **4. RUN**.
Each recipe lists the index it needs.

Collections used: `db_article` (`fk_user_id`, `slug`, `title`, `body`, `status`, `view_count`)
and `db_user` (`fk_user_id`, `name`, ...). Both are registered in `model.py`.
`_to_int` and `ALLOWED_STATUS` are module-level in the proc (see `examples/flask-api.md`).

---

## 1. Newest list (most common)

Index: `[("is_deleted", 1), ("status", 1), ("rec_timestamp", -1)]`

```python
def list_latest(self, limit):
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
    cursor = cursor.limit(limit)

    recs = list(cursor)
    return recs
# end def
```

## 2. One record (detail page)

Index: `[("slug", 1), ("is_deleted", 1)]`

```python
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
```

## 3. Exists check (tiny response)

```python
def slug_exists(self, slug):
    query = {}
    query["slug"] = slug
    query["is_deleted"] = False

    rec = self.mgdDB.db_article.find_one(query, {"_id": 1})
    return rec != None
# end def
```

## 4. Optional filters (build the query step by step)

Index: `[("is_deleted", 1), ("fk_user_id", 1), ("status", 1), ("rec_timestamp", -1)]`
(equality fields first, then the sort field).

```python
def filter_articles(self, params):
    user_id = (params.get("user_id") or "").strip()
    status = (params.get("status") or "").strip().upper()
    date_from = _to_int(params.get("from_ts"), 0)

    query = {}
    query["is_deleted"] = False
    if user_id != "":
        query["fk_user_id"] = user_id
    # end if
    if status in ALLOWED_STATUS:
        query["status"] = status
    # end if
    if date_from > 0:
        query["rec_timestamp"] = {"$gte": date_from}
    # end if

    projection = {}
    projection["_id"] = 0
    projection["slug"] = 1
    projection["title"] = 1
    projection["status"] = 1

    cursor = self.mgdDB.db_article.find(query, projection)
    cursor = cursor.sort("rec_timestamp", -1)
    cursor = cursor.limit(50)

    recs = list(cursor)
    return recs
# end def
```

Optional filters create different query shapes. Index the shapes that are
actually used on a page (for example "by user" and "by status"), not every
combination; the limit keeps the rare un-indexed shape cheap.

## 5. Page numbers + total (skip / limit)

Index: same as recipe 1.

```python
def list_page(self, page, page_size):
    page = _to_int(page, 1)
    if page < 1:
        page = 1
    # end if
    page_size = _to_int(page_size, 20)
    if page_size < 1 or page_size > 50:
        page_size = 20
    # end if

    query = {}
    query["is_deleted"] = False
    query["status"] = "PUBLISHED"

    projection = {}
    projection["_id"] = 0
    projection["slug"] = 1
    projection["title"] = 1

    cursor = self.mgdDB.db_article.find(query, projection)
    cursor = cursor.sort("rec_timestamp", -1)
    cursor = cursor.skip((page - 1) * page_size)
    cursor = cursor.limit(page_size)

    result = {}
    result["items"] = list(cursor)
    result["total"] = self.mgdDB.db_article.count_documents(query)
    result["page"] = page
    return result
# end def
```

## 6. "Load more" / infinite scroll (fast at any depth)

No `skip`: the client sends the last `rec_timestamp` it saw. Cost stays the
same on page 1 or page 10,000. Index: same as recipe 1.

```python
def list_after(self, last_ts, limit):
    last_ts = _to_int(last_ts, 0)

    query = {}
    query["is_deleted"] = False
    query["status"] = "PUBLISHED"
    if last_ts > 0:
        query["rec_timestamp"] = {"$lt": last_ts}
    # end if

    projection = {}
    projection["_id"] = 0
    projection["slug"] = 1
    projection["title"] = 1
    projection["rec_timestamp"] = 1

    cursor = self.mgdDB.db_article.find(query, projection)
    cursor = cursor.sort("rec_timestamp", -1)
    cursor = cursor.limit(limit)

    recs = list(cursor)
    next_ts = 0
    if len(recs) == limit:
        next_ts = recs[-1]["rec_timestamp"]
    # end if
    return {"items": recs, "next_ts": next_ts}
# end def
```

`rec_timestamp` is in milliseconds, so ties are rare. If records are created
in bulk (same millisecond), sort by `[("rec_timestamp", -1), ("pkey", -1)]`
and page with both values.

## 7. Search by title prefix (index-friendly)

Index: `[("is_deleted", 1), ("title", 1)]`

`import re` goes at the top of the proc file, after the `sys.path` header.

```python
def search_title(self, keyword):
    keyword = (keyword or "").strip()
    if keyword == "" or len(keyword) > 100:
        return []
    # end if

    query = {}
    query["is_deleted"] = False
    query["title"] = {"$regex": "^" + re.escape(keyword)}

    projection = {}
    projection["_id"] = 0
    projection["slug"] = 1
    projection["title"] = 1

    cursor = self.mgdDB.db_article.find(query, projection)
    cursor = cursor.limit(20)

    recs = list(cursor)
    return recs
# end def
```

`re.escape` stops users from injecting regex. Anchored `^` + case-sensitive
uses the index; `"$options": "i"` or no `^` scans the whole collection.

## 8. Join two collections without N+1

Index on `db_user`: `[("fk_user_id", 1), ("is_deleted", 1)]`

`articles` is a list loaded with `projection["fk_user_id"] = 1` (e.g. recipe 1 plus that field).

```python
def attach_authors(self, articles):
    # collect ids once (set = no duplicates)
    user_ids = set()
    for article in articles:
        user_ids.add(article["fk_user_id"])
    # end for

    # ONE query for all users
    query = {}
    query["fk_user_id"] = {"$in": list(user_ids)}
    query["is_deleted"] = False

    projection = {}
    projection["_id"] = 0
    projection["fk_user_id"] = 1
    projection["name"] = 1

    user_by_id = {}
    for user in self.mgdDB.db_user.find(query, projection):
        user_by_id[user["fk_user_id"]] = user
    # end for

    # map in memory (dict lookup, no extra queries)
    for article in articles:
        author = user_by_id.get(article["fk_user_id"], {})
        article["author_name"] = author.get("name", "")
    # end for
    return articles
# end def
```

2 queries total (the list + the users), no matter how many articles.

## 9. Partial update + not-found check (1 round trip)

```python
def set_status(self, slug, status):
    if status not in ALLOWED_STATUS:
        return {"status": "ERROR", "desc": "Invalid status"}
    # end if

    query = {}
    query["slug"] = slug
    query["is_deleted"] = False

    changes = {}
    changes["status"] = status

    result = self.mgdDB.db_article.update_one(query, {"$set": changes})
    if result.matched_count == 0:
        return {"status": "ERROR", "desc": "Article not found"}
    # end if
    return {"status": "SUCCESS", "desc": "Status updated"}
# end def
```

## 10. Atomic counter

```python
def add_view(self, slug):
    query = {}
    query["slug"] = slug
    query["is_deleted"] = False

    self.mgdDB.db_article.update_one(query, {"$inc": {"view_count": 1}})
# end def
```

## 11. Soft delete many

```python
def delete_by_user(self, user_id):
    query = {}
    query["fk_user_id"] = user_id
    query["is_deleted"] = False

    result = self.mgdDB.db_article.update_many(query, {"$set": {"is_deleted": True}})
    return {"status": "SUCCESS", "desc": str(result.modified_count) + " articles deleted"}
# end def
```

## 12. Different updates in one call (bulk)

`from pymongo import UpdateOne` goes at the top of the proc file.

```python
def reorder(self, slug_list):
    ops = []
    position = 0
    for slug in slug_list:
        ops.append(UpdateOne(
            {"slug": slug, "is_deleted": False},
            {"$set": {"order": position}}
        ))
        position = position + 1
    # end for
    if len(ops) == 0:
        return {"status": "ERROR", "desc": "Nothing to reorder"}
    # end if

    self.mgdDB.db_article.bulk_write(ops, ordered=False)
    return {"status": "SUCCESS", "desc": "Order saved"}
# end def
```

(Needs an `order` field in the `db_article` schema.)

## 13. Aggregation: count per status

Write the pipeline step by step too. `$match` always first so it can use an index.

```python
def count_per_status(self):
    pipeline = []
    pipeline.append({"$match": {"is_deleted": False}})
    pipeline.append({"$group": {"_id": "$status", "total": {"$sum": 1}}})
    pipeline.append({"$sort": {"total": -1}})

    counts = {}
    for row in self.mgdDB.db_article.aggregate(pipeline):
        counts[row["_id"]] = row["total"]
    # end for
    return counts
# end def
```

## 14. Aggregation: top authors this week, with names

```python
def top_authors(self, since_ts, limit):
    pipeline = []
    pipeline.append({"$match": {"is_deleted": False, "rec_timestamp": {"$gte": since_ts}}})
    pipeline.append({"$group": {"_id": "$fk_user_id", "total": {"$sum": 1}}})
    pipeline.append({"$sort": {"total": -1}})
    pipeline.append({"$limit": limit})
    pipeline.append({"$lookup": {
        "from": "db_user",
        "localField": "_id",
        "foreignField": "fk_user_id",
        "as": "user"
    }})
    pipeline.append({"$project": {
        "_id": 0,
        "fk_user_id": "$_id",
        "total": 1,
        "name": {"$arrayElemAt": ["$user.name", 0]}
    }})

    recs = list(self.mgdDB.db_article.aggregate(pipeline))
    return recs
# end def
```

`$limit` before `$lookup`, so only `limit` users are looked up.
Index on `db_user.fk_user_id` makes the `$lookup` fast.

## 15. User-chosen sort (whitelist)

```python
SORT_OPTIONS = {
    "newest": [("rec_timestamp", -1)],
    "oldest": [("rec_timestamp", 1)],
    "popular": [("view_count", -1)]
}

def list_sorted(self, sort_key):
    sort_by = SORT_OPTIONS.get(sort_key, SORT_OPTIONS["newest"])

    query = {}
    query["is_deleted"] = False
    query["status"] = "PUBLISHED"

    projection = {}
    projection["_id"] = 0
    projection["slug"] = 1
    projection["title"] = 1

    cursor = self.mgdDB.db_article.find(query, projection)
    cursor = cursor.sort(sort_by)
    cursor = cursor.limit(20)

    recs = list(cursor)
    return recs
# end def
```

Each option needs its own index, e.g. `"popular"` ->
`[("is_deleted", 1), ("status", 1), ("view_count", -1)]`.
