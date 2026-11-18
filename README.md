# Agoda Unit Testing Report

This repository contains the executed pytest suite for five selected Agoda backend modules: Hotels, Rooms, Bookings, Payments and Promotions. It includes the exact imported application source needed to reproduce the tests. `source_sha256.json` records the original source hashes. Production business logic has not been repaired or instrumented to change the results.

## Results from 18 November 2026

589 tests: 536 passed, 53 failed, no setup/teardown errors and no skipped tests. Failures are retained as executable defect regressions. Pytest returns exit code 1 because of these failures.

Statement coverage: 96.66%. Branch coverage: 91.64%. Combined coverage reported by pytest-cov: 95.45%. Counts are weighted by measured execution opportunities, not averaged across file percentages.

## Run

Use Python 3.12.10. From the repository root:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-test.txt
.venv/Scripts/python.exe -m pytest --cov --cov-branch --cov-report=term-missing --cov-report=html:work/evidence/coverage_html --cov-report=json:work/evidence/coverage.json --cov-report=xml:work/evidence/coverage.xml --junitxml=work/evidence/junit.xml --json-report --json-report-file=work/evidence/pytest_report.json --tb=short -q --disable-warnings
```

`pytest.ini` adds `backend` and `work` to the import path. New execution artifacts are written to `work/evidence`. The delivered original run is under `evidence`. The original local execution used the supplied nested backend directory; its imported files are byte-for-byte identical to the snapshot here.

## Scope and interpretation

- The five modules' complete models, serializers, views and runtime constants are in the coverage denominator. Tests, migrations, admin registration, app metadata, URL declarations and package markers are excluded and are not represented as tested business logic.
- SQLite runs in memory. Every test compares all registered model rows before and after a savepoint rollback, including failure cases. pytest-django also rolls back its outer test transaction. All 589 teardown audits succeeded in the delivered run.
- Tests of ORM changes check persisted rows or compare read-only snapshots. Payment gateway calls, notification delivery and filesystem deletion are mocked at their external boundary. Some serializer filter tests mock parent representation and use explicit interface doubles. `PR-ACTUAL01` independently records the real ActivityPromotion adapter defect.
- Coverage measures execution, including execution by failing tests. Import-time model/serializer declarations are counted by coverage.py. A high percentage is not a correctness claim.
- The real MySQL dialect, schema migration history, concurrent transactions, live Stripe settlement, email/Redis delivery, frontend UI and separate Accounts/Flights/Cars/Activities feature suites remain outside this five-module unit report. Related service records are real DB fixtures used to exercise Booking, Payment and Promotion behavior. No earlier system test or security review is claimed.
- No application branches are excluded with new `pragma: no cover` directives. Uncovered branches include unreachable defensive paths and code blocked by existing upstream errors. Their exact source line and branch IDs are available in the JSON/HTML reports.

## Evidence

`evidence/pytest_execution.log`, `junit.xml`, `pytest_report.json`, `results.json`, `coverage.json`, `coverage.xml` and `coverage_html/index.html` come from one complete pytest-cov run. `results.json` maps every report case ID to its pytest node ID, metadata, outcome, failure traceback and rollback audit.

The Excel report follows the supplied eight-sheet template. PASS notes are empty. FAIL notes explain the observed discrepancy. Sources and execution locators are stored as Excel cell notes, with no source column.

The original application backend is identified in the supplied thesis as https://github.com/nam-Space/agoda-be. This test repository was specified by the user as https://github.com/Lumith226/SQA-agoda.
