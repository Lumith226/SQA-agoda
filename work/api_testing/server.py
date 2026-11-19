"""Serve original Django APIs over localhost with a test-only DB audit boundary.

Postman explicitly begins each test case, executes its HTTP steps, asks for DB
observations and requests rollback. The same single WSGI thread owns the SQLite
transaction throughout. No application view/serializer/model is replaced.
Only Stripe's network boundary is doubled; mail and channels use memory backends.
"""
import argparse
from contextlib import ExitStack
from datetime import timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace
from unittest.mock import patch
from wsgiref.simple_server import make_server, WSGIRequestHandler

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'UnitTest/SQA-main/SQA-main/agoda-be'
if not BACKEND.exists():
    BACKEND = ROOT / 'backend'
sys.path[:0] = [str(BACKEND), str(ROOT / 'work'), str(Path(__file__).parent)]
os.environ['DJANGO_SETTINGS_MODULE'] = 'api_settings'
import django
django.setup()
from django.apps import apps
from django.core.management import call_command
from django.core.serializers.json import DjangoJSONEncoder
from django.core.wsgi import get_wsgi_application
from django.core.signals import got_request_exception
from django.db import transaction, connection
from rest_framework_simplejwt.tokens import AccessToken
from fixtures import seed_fixtures

ARTIFACTS = Path(__file__).parent / 'evidence'
ARTIFACTS.mkdir(parents=True, exist_ok=True)
AUDITS = {}
ACTIVE = None
CASES = {}

def capture_exception(sender, **kwargs):
    """Retain genuine application tracebacks for failed HTTP requests."""
    if ACTIVE is not None:
        ACTIVE.setdefault('request_errors', []).append(traceback.format_exc())

got_request_exception.connect(capture_exception, weak=False)

def snapshot():
    """Read all model and automatic many-to-many rows, including every field."""
    rows = {model._meta.label: list(model.objects.order_by('pk').values())
            for model in apps.get_models(include_auto_created=True)
            if model._meta.managed and not model._meta.proxy}
    return json.loads(json.dumps(rows, cls=DjangoJSONEncoder, sort_keys=True))

def digest(state):
    """Hash canonical full row data, so rollback checks cover values and relations."""
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()

def json_response(start_response, payload, status='200 OK'):
    """Emit JSON only from the separate test-control interface."""
    body = json.dumps(payload, cls=DjangoJSONEncoder).encode()
    start_response(status, [('Content-Type', 'application/json'), ('Content-Length', str(len(body)))])
    return [body]

def stripe_create(**arguments):
    """Record real checkout parameters without contacting the payment service."""
    ACTIVE['external_calls'].append({'operation': 'checkout.create', 'arguments': arguments})
    if ACTIVE['case'].get('stripe', {}).get('create_error'):
        raise RuntimeError('Test gateway unavailable')
    return SimpleNamespace(id='cs_api_test', url='https://checkout.example.test/cs_api_test')

def stripe_retrieve(session_id):
    """Choose paid/unpaid/error gateway observations from the declared fixture."""
    ACTIVE['external_calls'].append({'operation': 'checkout.retrieve', 'session_id': session_id})
    if ACTIVE['case'].get('stripe', {}).get('retrieve_error'):
        raise RuntimeError('Test gateway unavailable')
    return SimpleNamespace(payment_status=ACTIVE['case'].get('stripe', {}).get('payment_status', 'unpaid'),
        payment_intent='pi_api_test', id=session_id)

def stripe_refund(**arguments):
    """Keep refund requests observable while preventing a real refund."""
    ACTIVE['external_calls'].append({'operation':'refund.create', 'arguments':arguments})
    return SimpleNamespace(id='re_api_test',status='succeeded')

def begin(case_id):
    """Start one savepoint and arrange fixtures before Postman calls an API."""
    global ACTIVE
    if ACTIVE is not None:
        rollback(ACTIVE['id'], abandoned=True)
    case = CASES[case_id]
    baseline = snapshot()
    atomic = transaction.atomic()
    atomic.__enter__()
    ACTIVE = {'id':case_id,'case':case,'atomic':atomic,'baseline':baseline,'external_calls':[],'steps':[]}
    try:
        seed_fixtures(case.get('profile'))
    except Exception:
        transaction.set_rollback(True)
        atomic.__exit__(*sys.exc_info())
        ACTIVE = None
        raise
    tokens = {}
    for key, user_id in [('owner_token',1),('other_token',2)]:
        token = AccessToken()
        token['user_id'] = user_id
        tokens[key] = str(token)
    expired = AccessToken()
    expired['user_id'] = 1
    expired.set_exp(lifetime=timedelta(seconds=-5))
    tokens['expired_token'] = str(expired)
    return {'case_id':case_id,'fixture_ready':True,'tokens':tokens,'baseline_digest':digest(baseline)}

def rollback(case_id, abandoned=False):
    """Execute rollback even after assertion failures; independently compare all rows."""
    global ACTIVE
    if ACTIVE is None or ACTIVE['id'] != case_id:
        return {'case_id':case_id,'rollback_verified':False,'error':'No matching active transaction'}
    state = ACTIVE
    transaction.set_rollback(True)
    state['atomic'].__exit__(None,None,None)
    restored = snapshot()
    evidence = {'case_id':case_id,'baseline_digest':digest(state['baseline']),
        'restored_digest':digest(restored),'rollback_verified':state['baseline']==restored,
        'abandoned':abandoned,'steps':state['steps'],'external_calls':state['external_calls']}
    AUDITS[case_id] = evidence
    with (ARTIFACTS/'database_audit.jsonl').open('a',encoding='utf8') as stream:
        stream.write(json.dumps(evidence,cls=DjangoJSONEncoder)+'\n')
    ACTIVE = None
    return {key:value for key,value in evidence.items() if key not in ['steps','external_calls']}

DJANGO_APPLICATION = get_wsgi_application()

def application(environ, start_response):
    """Dispatch test controls separately; pass product requests to original Django."""
    path = environ['PATH_INFO']
    if path == '/__test__/health':
        return json_response(start_response,{'ready':True,'active_case':ACTIVE['id'] if ACTIVE else None})
    if path.startswith('/__test__/begin/'):
        return json_response(start_response,begin(path.rstrip('/').rsplit('/',1)[1]))
    if path.startswith('/__test__/rollback/'):
        return json_response(start_response,rollback(path.rstrip('/').rsplit('/',1)[1]))
    if path.startswith('/__test__/inspect/'):
        case_id = path.rstrip('/').rsplit('/',1)[1]
        if ACTIVE is None or ACTIVE['id'] != case_id or not ACTIVE['steps']:
            return json_response(start_response,{'error':'No matching API observation'},'409 Conflict')
        return json_response(start_response,ACTIVE['steps'][-1])
    case_id = environ.get('HTTP_X_TEST_CASE_ID')
    if ACTIVE is None or ACTIVE['id'] != case_id:
        return json_response(start_response,{'error':'Begin the matching test case first'},'409 Conflict')
    before = snapshot()
    ACTIVE['request_errors'] = []
    status_seen = {}
    def capture_status(status, headers, exc_info=None):
        status_seen['status'] = int(status.split()[0])
        return start_response(status,headers,exc_info)
    started = time.perf_counter()
    response_iterable = DJANGO_APPLICATION(environ,capture_status)
    try:
        response_body = b''.join(response_iterable)
    finally:
        if hasattr(response_iterable,'close'):
            response_iterable.close()
    transaction_marked_for_rollback = connection.needs_rollback
    if transaction_marked_for_rollback:
        # An IntegrityError marks Django's surrounding test transaction broken.
        # SQLite still permits observation of its actual rows. Clear only that
        # flag for this audit; the whole case is explicitly rolled back later.
        transaction.set_rollback(False)
    after = snapshot()
    changed_models = [label for label in before if before[label] != after[label]]
    observation = {'case_id':case_id,'step':environ.get('HTTP_X_TEST_STEP_ID'),
        'method':environ['REQUEST_METHOD'],'path':path,'status':status_seen.get('status'),
        'duration_ms':round((time.perf_counter()-started)*1000,3),
        'response_sha256':hashlib.sha256(response_body).hexdigest(),
        'before_digest':digest(before),'after_digest':digest(after),
        'database_unchanged':before==after,'changed_models':changed_models,
        'transaction_marked_for_rollback':transaction_marked_for_rollback,
        'application_errors':list(ACTIVE['request_errors']),
        'tables':{label:{'before':before[label],'after':after[label]} for label in before
                  if label.split('.')[0] in ['hotels','rooms','bookings','payments','promotions','notifications']},
        'external_calls':list(ACTIVE['external_calls'])}
    ACTIVE['steps'].append(observation)
    return [response_body]

class QuietHandler(WSGIRequestHandler):
    """Keep one concise, genuine HTTP access log per request."""
    def log_message(self, format_string, *arguments):
        print(format_string % arguments,flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--cases',default=str(Path(__file__).parent/'cases.json'))
    parser.add_argument('--evidence-dir',default=str(ARTIFACTS))
    arguments = parser.parse_args()
    ARTIFACTS=Path(arguments.evidence_dir)
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    (ARTIFACTS/'database_audit.jsonl').write_text('',encoding='utf8')
    CASES = {case['id']:case for case in json.loads(Path(arguments.cases).read_text(encoding='utf8'))}
    call_command('migrate',run_syncdb=True,verbosity=0,interactive=False)
    # These patches replace external SDK transport calls only. ORM/view code is real.
    with ExitStack() as stack:
        stack.enter_context(patch('stripe.checkout.Session.create',side_effect=stripe_create))
        stack.enter_context(patch('stripe.checkout.Session.retrieve',side_effect=stripe_retrieve))
        stack.enter_context(patch('stripe.Refund.create',side_effect=stripe_refund))
        httpd = make_server('127.0.0.1',arguments.port,application,handler_class=QuietHandler)
        print(f'API test server listening at http://127.0.0.1:{arguments.port}',flush=True)
        try:
            httpd.serve_forever()
        finally:
            if ACTIVE:
                rollback(ACTIVE['id'],abandoned=True)
