---
name: python-backend-expert
description: Python backend expert for the SLAPZ (slapz102) Flask + MongoDB framework. Writes blueprints, views, procs, model schemas, and PyMongo queries in the house style (closing comments, no f-strings, schema-first models, soft delete, sanitize + CSRF) using an easy-to-read query style that stays index-friendly and fast. Use when adding or changing a feature module, route, view, proc, MongoDB query, aggregation, index, or test in this repo.
---

# Python Backend Expert (SLAPZ / slapz102)

`AGENTS.md` at the repo root is the source of truth. This skill shows how to
apply it quickly and how to write queries and logic that stay easy to read
and fast.

## Golden rules

1. Copy `slapz102_modules/sample/` when building anything new.
2. Keep the layers: `server.py` -> `<feature>_blueprint.py` -> `view/<feature>/view_<feature>.py` -> `<feature>_proc.py` -> `slapz102_core`.
3. Business logic and DB access live ONLY in the proc.
4. Every Python file starts with the `sys.path.append(...)` header. No relative imports.
5. House style: `# end if` / `# end for` / `# end def` / `# end class` / `# end try`, no f-strings, `== None` / `!= None`.
6. Register new collections in `slapz102_core/model.py` first. Create records with `database.new(...)` + `rec.put(...)` + `rec.insert()`.
7. Soft delete only (`is_deleted: True`), and every query filters `"is_deleted": False`.
8. User input goes through `sanitize.clean_html_dic(...)`; every POST view calls `csrf.validate()` first.
9. Blueprint routes wrap the view call in `try/except` -> `print(traceback.format_exc())` -> `"An error occurred", 500`.
10. Never touch `slapz102_core/` or `slapz102_stdlib/` beyond additions. Never commit `config.py`.

## Query style (easy to read, still fast)

Every query is written in 4 named steps, so anyone can read it top to bottom:

```python
# 1. WHAT  - which documents
query = {}
query["is_deleted"] = False
query["status"] = "PUBLISHED"

# 2. WHICH FIELDS - only what the caller needs
projection = {}
projection["_id"] = 0
projection["slug"] = 1
projection["title"] = 1

# 3. HOW - order and size (always bounded)
cursor = self.mgdDB.db_article.find(query, projection)
cursor = cursor.sort("rec_timestamp", -1)
cursor = cursor.limit(20)

# 4. RUN
recs = list(cursor)
```

Performance must-haves (details in the MongoDB reference):

- Every list query has a matching index (equality fields -> sort field -> range field).
- Projection is mandatory by default: list only the fields needed, never sensitive fields (passwords, tokens).
- Avoid `$regex` (non-prefix), `$where`, `$ne`, `$nin`, `$not`, un-indexed `$or`, and large `$skip`.
- Always `limit()` lists; cap user-supplied page sizes.
- Never run a query inside a `for` loop: batch with `$in`, then map with a dict.
- Use atomic operators (`$set`, `$inc`) and check `matched_count` instead of read-then-write.

## Logic style (simple, explicit, fast)

- Read and clean params at the top: `title = (params.get("title") or "").strip()`.
- Guard clauses first, each returning `{"status": "ERROR", "desc": "..."}` early.
- Write methods return `{"status": "SUCCESS", "desc": "...", "data": ...}`; read methods return the record / list (or `None`).
- One DB round trip per need; reuse results you already loaded.
- Use dicts and sets for lookups (O(1)) instead of nested loops (O(n*m)).
- Move invariant work (constants, compiled regex, `set(...)` of ids) outside loops.
- Explicit `for` loops by default; a comprehension only for one simple expression.
- Small private helpers (`_to_int`, `_slugify`) at module level, like `sample_proc.py`.
- Optimization priority: DB/network round trips -> algorithm/data structure -> CPU -> memory -> micro-optimizations (only when measured).
- Never sacrifice readability for negligible gains, or correctness for speed.

## References

When working with Flask:
Read `references/flask-guidelines.md`.

When writing, reviewing, or optimizing any Python code (proc, view, helper, test):
Read `references/python-performance.md`.

When working with MongoDB:
Read `references/mongodb-patterns.md`.

When writing, reviewing, or optimizing any MongoDB query or aggregation:
Read `references/mongodb-performance.md`.

## Examples

When building a new feature module, route, or JSON API:
Read `examples/flask-api.md`.

When writing a MongoDB query (list, detail, filter, search, paginate, update, aggregate):
Read `examples/mongodb-query.md`.

## Finish checklist

- [ ] Collection registered in `model.py` (additions only)
- [ ] Indexes created for every new list / lookup query
- [ ] Blueprint registered in `server.py`
- [ ] POST forms carry `csrf_token`; views validate it
- [ ] Python review checklist in `references/python-performance.md` passes
- [ ] Tests added in `tests/`, and `python3 -m pytest tests/ -v` passes
