"""Reconcile real Newman assertions with independent DB audits and HTTP bytes."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

DIRECTORY=Path(__file__).parent
CASES=json.loads((DIRECTORY/'cases.json').read_text(encoding='utf8'))
CASE_PATTERN=re.compile(r'^(API-(?:PR|[HRBP])-\d{3})')

def reconcile(report_path, audit_path, output_path):
    """Derive case outcomes from executed assertions, never from expected statuses."""
    report=json.loads(Path(report_path).read_text(encoding='utf8'))
    all_audits=[json.loads(line) for line in Path(audit_path).read_text(encoding='utf8').splitlines() if line.strip()]
    audits={audit['case_id']:audit for audit in all_audits[-150:]}
    assert len(audits)==150,'Incomplete per-case DB audits'
    results=[]
    for case in CASES:
        executions=[execution for execution in report['run']['executions']
            if CASE_PATTERN.match(execution['item']['name']) and CASE_PATTERN.match(execution['item']['name']).group(1)==case['id']]
        assert len(executions)==2*len(case['steps'])+2,(case['id'],len(executions))
        assertions=[assertion for execution in executions for assertion in execution.get('assertions',[])]
        assert len(assertions)==3*len(case['steps'])+2,(case['id'],len(assertions))
        failed=[{'request':execution['item']['name'],'assertion':assertion['assertion'],
                 'message':assertion['error']['message']}
                for execution in executions for assertion in execution.get('assertions',[]) if assertion.get('error')]
        network_errors=[execution.get('requestError') for execution in executions if execution.get('requestError')]
        observed=[]
        audit=audits[case['id']]
        assert audit['rollback_verified'] and not audit['abandoned'],case['id']
        for operation,observation in zip(case['steps'],audit['steps'],strict=True):
            matching=[execution for execution in executions
                if execution['item']['name'].startswith(operation['id']+' | '+operation['method']+' ')]
            assert len(matching)==1,operation['id']
            execution=matching[0]
            response=execution['response']
            raw_bytes=bytes(response['stream']['data'])
            assert hashlib.sha256(raw_bytes).hexdigest()==observation['response_sha256'],operation['id']
            assert response['code']==observation['status'],operation['id']
            observed.append({'id':operation['id'],'method':operation['method'],'path':operation['path'],
                'status':response['code'],'response_body':raw_bytes.decode('utf8',errors='replace'),
                'database_unchanged':observation['database_unchanged'],
                'changed_models':observation['changed_models'],'application_errors':observation['application_errors'],
                'duration_ms':observation['duration_ms']})
        results.append({**case,'status':'ERROR' if network_errors else ('FAIL' if failed else 'PASS'),
            'failures':failed,'assertions':len(assertions),'observed_steps':observed,
            'rollback_verified':audit['rollback_verified'],'database_audit':audit})
    inventory=json.loads((DIRECTORY/'endpoint_inventory.json').read_text(encoding='utf8'))
    coverage=[]
    for endpoint in inventory:
        parts=re.split(r'(<[^>]+>)',endpoint['path'])
        pattern=''.join('[^/]+' if part.startswith('<') else re.escape(part) for part in parts)
        matching=[(case,operation) for case in results for operation in case['observed_steps']
            if operation['method']==endpoint['method'] and re.fullmatch(pattern,operation['path'].split('?')[0])]
        coverage.append({**endpoint,'executed':bool(matching),'case_ids':sorted({case['id'] for case,_ in matching}),
                         'requests':len(matching),'http_statuses':sorted({operation['status'] for _,operation in matching})})
    summary={'test_cases':len(results),'module_case_counts':Counter(case['module'] for case in results),
        'outcomes':Counter(case['status'] for case in results),'api_requests':sum(len(case['steps']) for case in results),
        'db_observation_requests':sum(len(case['steps']) for case in results),'setup_cleanup_requests':len(results)*2,
        'http_requests':report['run']['stats']['requests']['total'],
        'assertions':report['run']['stats']['assertions']['total'],'failed_assertions':report['run']['stats']['assertions']['failed'],
        'rollback_verified':sum(case['rollback_verified'] for case in results),
        'endpoint_method_pairs':len(coverage),'executed_endpoint_method_pairs':sum(endpoint['executed'] for endpoint in coverage),
        'timings':report['run']['timings']}
    assert summary['failed_assertions']==sum(len(case['failures']) for case in results)
    payload={'summary':summary,'cases':results,'endpoint_coverage':coverage}
    Path(output_path).write_text(json.dumps(payload,indent=2,ensure_ascii=True),encoding='utf8')
    print(json.dumps(summary,indent=2))
    for case in results:
        if case['status']!='PASS':
            print(case['id']+': '+'; '.join(failure['message'] for failure in case['failures']))
    return payload

if __name__=='__main__':
    reconcile(sys.argv[1],sys.argv[2],sys.argv[3])
