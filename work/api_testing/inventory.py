"""Inventory reachable method/path pairs, excluding duplicate and format routes."""
import json
import os
import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'UnitTest/SQA-main/SQA-main/agoda-be'
if not BACKEND.exists():
    BACKEND = ROOT / 'backend'
sys.path[:0] = [str(BACKEND), str(ROOT / 'work'), str(Path(__file__).parent)]
os.environ['DJANGO_SETTINGS_MODULE'] = 'api_settings'
import django
django.setup()
from django.urls import URLResolver, get_resolver

def inventory(resolver=None, prefix=''):
    """Resolve declared views into the HTTP methods actually exposed by DRF."""
    found = {}
    for route in (resolver or get_resolver()).url_patterns:
        pattern = prefix + str(route.pattern)
        if isinstance(route, URLResolver):
            for endpoint in inventory(route, pattern):
                found.setdefault((endpoint['method'], endpoint['path']), endpoint)
            continue
        if 'format' in pattern or route.name in ['api-root', 'payment-root', 'booking-root']:
            continue
        callback = route.callback
        view_class = getattr(callback, 'cls', getattr(callback, 'view_class', None))
        if view_class is None:
            continue
        actions = getattr(callback, 'actions', {})
        methods = actions.keys() if actions else view_class.http_method_names
        for method in methods:
            if method in ['head', 'options']:
                continue
            if not actions and not hasattr(view_class, method):
                continue
            canonical = re.sub(r'\(\?P<(\w+)>[^)]+\)', r'<\1>', pattern)
            endpoint = dict(method=method.upper(), path='/' + canonical.replace('^', '').replace('$', ''),
                            view=view_class.__name__, module=view_class.__module__.split('.')[0],
                            action=actions.get(method), name=route.name)
            found.setdefault((endpoint['method'], endpoint['path']), endpoint)
    return list(found.values())

if __name__ == '__main__':
    endpoints = inventory()
    target = Path(__file__).parent / 'endpoint_inventory.json'
    target.write_text(json.dumps(endpoints, indent=2), encoding='utf8')
    from collections import Counter
    print(json.dumps({'endpoint_method_pairs': len(endpoints), 'modules': Counter(e['module'] for e in endpoints)}, indent=2))
