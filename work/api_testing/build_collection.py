"""Export standard Postman v2.1 requests with explicit case-ID comments.

Newman executes exactly the same scripts that can be imported into Postman.
Setup and rollback are visible requests, so cleanup is independently reportable.
"""
import json
from pathlib import Path

DIRECTORY = Path(__file__).parent
CASES = json.loads((DIRECTORY/'cases.json').read_text(encoding='utf8'))
ASSERTIONS = (DIRECTORY/'postman_assertions.js').read_text(encoding='utf8')
RESPONSE_ASSERTIONS = ASSERTIONS.split('// Read test-only observations')[0]
HELPERS = ASSERTIONS.split('// Assert the API contract')[0]
DB_ASSERTIONS = ASSERTIONS[ASSERTIONS.index("    pm.test(caseId + ' ' + stepId + ': CheckDB'"):].rsplit('});',1)[0]
DB_ASSERTIONS = DB_ASSERTIONS.replace("        pm.expect(error, 'DB observation transport').to.equal(null);\n",'')

def event(source):
    """Build a documented post-response event using Postman's native test API."""
    return [{'listen':'test','script':{'type':'text/javascript','exec':source.splitlines()}}]

def control_item(case, kind):
    """Keep fixture setup and rollback checks visible in both Postman and logs."""
    case_id = case['id']
    if kind == 'begin':
        script = f'''// Test Case ID: {case_id}
// Arrange: create isolated reference/contrast rows and fresh real JWTs.
pm.test('{case_id}: isolated fixtures are ready', () => {{
    pm.expect(pm.response.code).to.equal(200);
    const state = pm.response.json();
    pm.expect(state.case_id).to.equal('{case_id}');
    pm.expect(state.fixture_ready).to.equal(true);
    Object.keys(state.tokens).forEach(key => pm.collectionVariables.set(key, state.tokens[key]));
}});'''
    else:
        script = f'''// Test Case ID: {case_id}
// Rollback: execute the savepoint rollback after all response/DB assertions.
// Compare canonical snapshots of every model and M2M table with pre-test data.
pm.test('{case_id}: database restored to BEFORE the test', () => {{
    pm.expect(pm.response.code).to.equal(200);
    const audit = pm.response.json();
    pm.expect(audit.case_id).to.equal('{case_id}');
    pm.expect(audit.abandoned).to.equal(false);
    pm.expect(audit.rollback_verified).to.equal(true);
    pm.expect(audit.restored_digest).to.equal(audit.baseline_digest);
}});'''
    return {'name':f'{case_id} | {kind.upper()}',
            'request':{'method':'POST','url':f'{{{{base_url}}}}/__test__/{kind}/{case_id}',
                       'description':case['objective']},'event':event(script)}

def api_item(case, operation):
    """Bind declared expectations and CheckDB assertions to a real API request."""
    case_id, step_id = case['id'], operation['id']
    headers = [{'key':'Accept','value':'application/json'},
               {'key':'X-Test-Case-ID','value':case_id},{'key':'X-Test-Step-ID','value':step_id}]
    if operation['auth']:
        token = 'malformed.jwt.token' if operation['auth']=='invalid' else '{{'+operation['auth']+'}}'
        headers.append({'key':'Authorization','value':'Bearer '+token})
    request = {'method':operation['method'],'url':'{{base_url}}'+operation['path'],
               'header':headers,'description':case['objective']+'\n\nExpected contract:\n'+json.dumps(operation['expect'],indent=2)}
    if operation['body'] is not None or operation['raw'] is not None:
        headers.append({'key':'Content-Type','value':'application/json'})
        request['body'] = {'mode':'raw','raw':operation['raw'] if operation['raw'] is not None else json.dumps(operation['body']),
                           'options':{'raw':{'language':'json'}}}
    source = f'// Test Case ID: {case_id}\n// Step ID: {step_id}\n// Act: {operation["method"]} {operation["path"]}\n'
    source += f'const caseId = {json.dumps(case_id)};\nconst stepId = {json.dumps(step_id)};\n'
    declaration=source+'const expected = '+json.dumps(operation['expect'])+';\n'
    response_source=declaration+RESPONSE_ASSERTIONS+"\npm.collectionVariables.set(stepId + '_response_hash', require('crypto-js').SHA256(pm.response.text()).toString());"
    api_request={'name':f'{step_id} | {operation["method"]} {operation["path"]}', 'request':request,'event':event(response_source)}
    audit_source=declaration+HELPERS+"\nconst auditResponse=pm.response;\nconst responseHash=pm.collectionVariables.get(stepId + '_response_hash');\n"+DB_ASSERTIONS
    db_request={'name':f'{step_id} | CHECK DATABASE',
        'request':{'method':'GET','url':f'{{{{base_url}}}}/__test__/inspect/{case_id}',
                   'description':'Observe actual persisted rows immediately after '+step_id+'. No application logic or data repair is performed.'},
        'event':event(audit_source)}
    return [api_request,db_request]

collection = {'info':{'name':'Agoda API Integration Tests - 150 Cases',
    'schema':'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
    'description':'30 cases per selected module. Original application HTTP routes, real JWT and SQLite ORM. Explicit per-case setup, response and CheckDB assertions, and audited rollback. Stripe transport uses a declared test double.'},
    'variable':[{'key':'base_url','value':'http://127.0.0.1:8765'}], 'item':[]}
for module in ['Hotels','Rooms','Bookings','Payments','Promotions']:
    folders=[]
    for case in [entry for entry in CASES if entry['module']==module]:
        folders.append({'name':case['id']+' | '+case['objective'],
                        'item':[control_item(case,'begin')]+[item for operation in case['steps'] for item in api_item(case,operation)]+[control_item(case,'rollback')]})
    collection['item'].append({'name':module,'item':folders})
target = DIRECTORY/'Agoda_API_Tests.postman_collection.json'
target.write_text(json.dumps(collection,indent=2),encoding='utf8')
environment={'id':'agoda-isolated-local-api','name':'Agoda isolated localhost',
    'values':[{'key':'base_url','value':'http://127.0.0.1:8765','enabled':True}],
    '_postman_variable_scope':'environment'}
(DIRECTORY/'Agoda_Local.postman_environment.json').write_text(json.dumps(environment,indent=2),encoding='utf8')
print(f'Exported {len(CASES)} cases and {sum(len(case["steps"])*2+2 for case in CASES)} visible collection requests.')
