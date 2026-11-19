"""Run the complete Postman collection against a temporary local Django server.

The output folder is an execution artifact directory and its logs are replaced
on each run. The original application source and any production DB are untouched.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
DIRECTORY=Path(__file__).parent

def run():
    """Start isolated HTTP service, run Newman, keep actual logs and stop service."""
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',default=str(DIRECTORY/'evidence'))
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--newman-path',help='Optional existing Newman entry point for an independent reproduction')
    arguments=parser.parse_args()
    output=Path(arguments.output_dir).resolve()
    output.mkdir(parents=True,exist_ok=True)
    runtime=ROOT/'work/postman_runtime'
    newman=Path(arguments.newman_path).resolve() if arguments.newman_path else runtime/'node_modules/newman/bin/newman.js'
    if not newman.exists():
        npm=shutil.which('npm.cmd') or shutil.which('npm')
        subprocess.run([npm,'install','--prefix',str(runtime),'--cache',str(ROOT/'work/npm-cache'),
                        'newman@6.2.1','--no-audit','--no-fund'],check=True,cwd=ROOT)
    collection=ROOT/'postman/Agoda_API_Tests.postman_collection.json'
    if not collection.exists(): collection=DIRECTORY/collection.name
    command=[shutil.which('node'),str(newman),'run',str(collection),
        '--env-var',f'base_url=http://127.0.0.1:{arguments.port}',
        '--reporters','cli,json,junit','--reporter-json-export',str(output/'newman_report.json'),
        '--reporter-junit-export',str(output/'newman_junit.xml'),
        '--reporter-cli-no-assertions','--reporter-cli-no-failures','--disable-unicode','--color','off',
        '--timeout-request','15000','--timeout-script','15000']
    metadata={'python':sys.version,'node':subprocess.check_output(['node','--version'],text=True).strip(),
              'newman':'6.2.1','command':command,'database':'isolated in-memory SQLite',
              'service_doubles':['Stripe checkout/refund transport','in-memory mail/channel delivery']}
    with (output/'server.log').open('wb') as server_log:
        process=subprocess.Popen([sys.executable,'-X','utf8','-u',str(DIRECTORY/'server.py'),
            '--port',str(arguments.port),'--evidence-dir',str(output)],cwd=ROOT,
            stdout=server_log,stderr=subprocess.STDOUT)
        try:
            for attempt in range(100):
                if process.poll() is not None: raise RuntimeError('Test server exited; inspect server.log')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{arguments.port}/__test__/health',timeout=1) as response:
                        if json.load(response)['ready']: break
                except OSError: time.sleep(0.1)
            else: raise RuntimeError('Test server did not become ready')
            print('Executing 150 Postman cases (30 per module) over real localhost HTTP.',flush=True)
            with (output/'newman_execution.log').open('wb') as execution_log:
                completed=subprocess.run(command,cwd=ROOT,stdout=execution_log,stderr=subprocess.STDOUT)
            metadata['newman_exit_code']=completed.returncode
            with urllib.request.urlopen(f'http://127.0.0.1:{arguments.port}/__test__/health',timeout=2) as response:
                metadata['active_transaction_after_run']=json.load(response)['active_case']
            assert metadata['active_transaction_after_run'] is None,'Collection left an active transaction'
        finally:
            process.terminate()
            process.wait(timeout=10)
    (output/'environment.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')
    print(f'Newman exit code {completed.returncode}. Actual logs/reports saved to {output}',flush=True)
    return completed.returncode

if __name__=='__main__':
    raise SystemExit(run())
