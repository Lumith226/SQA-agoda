# Agoda API testing with Postman

The report contains 150 business cases: 30 each for Hotels, Rooms, Bookings,
Payments and Promotions. Multi-step cases execute 218 target API requests and
exercise all 124 declared HTTP method/endpoint pairs. Setup, DB observations
and rollback bring the total to 736 HTTP requests. The collection makes 954
assertions. Read `api-evidence/results.json` for actual case outcomes.

## Run with Newman

Use Python 3.12 and Node.js. From the repository root:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-test.txt
.venv/Scripts/python.exe work/api_testing/run_all.py
```

The runner installs pinned Newman 6.2.1 into `work/postman_runtime` if absent,
starts the localhost Django server, runs the collection, saves real CLI/JSON/
JUnit and DB audit evidence into `work/api_testing/evidence`, and stops the
server. That generated folder is replaced by subsequent runs. Existing product
defects intentionally fail assertions, so Newman/runner exit code 1 is expected.
Do not use an exit-code suppression flag to turn those failures into success.

## Run inside Postman

Start the same isolated server and keep its terminal open:

```powershell
.venv/Scripts/python.exe work/api_testing/server.py --evidence-dir work/api_testing/manual_evidence
```

Import `postman/Agoda_API_Tests.postman_collection.json` and
`postman/Agoda_Local.postman_environment.json` into Postman. Select the local
environment and run the whole collection (or one complete case folder) in
Collection Runner. Keep BEGIN, API, CHECK DATABASE and ROLLBACK requests in
their existing order. The scripts are standard Postman v2.1 JavaScript; no
Postman cloud account or API key is required to run the local collection.

## Response assertions, CheckDB and rollback

1. BEGIN creates two distinct owner/city/hotel/service graphs and fresh signed
   JWTs inside a transaction. A third booking has no payment for insert tests.
2. The target request traverses the original Django URL/view/serializer/model
   code over real localhost HTTP. No APIRequestFactory or forced authentication
   is used in this API suite.
3. Postman asserts status, response shape, exact selected IDs, field values or
   error messages. Expected contracts are declared in `cases.json` before the
   operation and never copied from a response.
4. CHECK DATABASE reads an observation of the real ORM rows immediately after
   that operation. A SHA-256 response digest binds the observation to the exact
   HTTP response bytes. Reads/rejections compare all table/field values; writes
   check exact counts, IDs, foreign keys, amounts, related records and unchanged
   unrelated rows. Expected update timestamps may advance.
5. ROLLBACK explicitly restores the transaction and compares all registered
   model and automatic M2M rows with the BEFORE-test snapshot. This request
   still executes when previous assertions fail. The runner also checks that
   no active test transaction remains at the end.

The separate `/__test__/` interface is only in the local harness, not an added
product API. SQLite is in memory. After an application IntegrityError the harness
clears Django's broken-transaction flag only to observe SQLite's actual rows;
it does not repair them. The complete case transaction is rolled back later.

## Scope and interpretation

Original application Python files and five module URL files are byte-identical
to the supplied project. `api-evidence/source_sha256.json` records those hashes.
JWT permissions and product response/validation behavior are exercised. Stripe
SDK transport calls use explicit checkout/refund doubles, while mail and channel
delivery use memory backends. Notification database records remain real.

MySQL dialect/schema migrations, concurrency, live Stripe settlement, external
mail delivery, frontend UI and modules outside the selected five are separate
test scopes. Endpoint execution coverage includes failed responses; 100% endpoint
coverage does not mean all cases pass and is not source-code coverage.

Case expectations follow source-defined fields and response contracts. Negative
room inventory is invalid domain input. The unbound PUT/PATCH methods on the
interaction collection route should reject the method rather than return a
server error. Exact original-language API error text remains in scripts/raw
evidence; report explanations are English.

## Deliverables and evidence

- `reports/5_API_Test_Report_EN.xlsx`: UnitTest-style English report; 150 Test IDs,
  multiple API rows where needed, empty PASS reasons, explained failures, no
  frozen/split panes and API endpoint execution coverage.
- `postman/`: importable collection and local environment.
- `api-evidence/newman_execution.log`: genuine saved Newman terminal output.
- `api-evidence/newman_report.json` and `newman_junit.xml`: native Newman reports.
  JSON whitespace is compacted without changing any value. The exact original
  Newman JSON export is also preserved in `newman_report.json.gz`.
- `api-evidence/database_audit.jsonl`: actual before/after ORM observations and
  rollback evidence. `results.json` reconciles the two independent sources.
- `api-evidence/report.html`: searchable case report derived from that execution.
- `api-evidence/verification.json`: independent replay and source/script checks.

Detailed comments, exact Test Case ID comments, descriptive naming, CheckDB and
rollback are documented in `api-evidence/script_requirements.json`.

Newman references: https://learning.postman.com/docs/collections/using-newman-cli/installing-running-newman
and https://learning.postman.com/docs/collections/using-newman-cli/newman-options
