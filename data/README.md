# `data/`

* `samples/sales_sample.csv` — a tiny, valid sales import for `POST /api/import/csv?kind=sales`.
* `samples/inventory_sample.csv` — a tiny, valid inventory import for `kind=inventory`.

The full demo dataset is generated deterministically at seed time by
`backend/app/seed/seed.py` (fixed RNG seed), so it is reproducible rather than checked in as
a large CSV dump.

## Importing

```bash
curl -X POST http://localhost:8000/api/import/csv \
  -H "Authorization: Bearer $TOKEN" \
  -F kind=sales \
  -F file=@data/samples/sales_sample.csv
```

Rows are validated server-side. Invalid rows (negative quantity, zero price, malformed SKU,
unparseable or future dates, unknown store, duplicates) are rejected individually and reported;
valid rows are still imported.
