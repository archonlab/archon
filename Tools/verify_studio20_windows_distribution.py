#!/usr/bin/env python3
"""Cross-platform STUDIO20 regression; never claims native Windows acceptance."""
from __future__ import annotations
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'Tools'))
from archon_windows_distribution import stage, verify, probe
from archon_runtime_python import runtime_python_command
from archon_distribution_stage import read_whitelist


def run(root, script, *args):
    env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1'
    p=subprocess.run([sys.executable,'-B',str(root/script),*map(str,args)],cwd=root,env=env,text=True,capture_output=True,timeout=120)
    assert p.returncode==0, p.stdout+p.stderr
    return p.stdout


def rejects(call):
    try:call()
    except (RuntimeError,AssertionError):return
    raise AssertionError('invalid input accepted')


def main():
    checks=[]
    contract=json.loads((ROOT/'Packaging/windows/distribution.json').read_text())
    assert contract['canonical_entrypoint']=='Tools/archon_studio_desktop.py'
    checks.append('Windows contract and canonical entrypoint')
    closure=['Universe_Search/search_launcher.py','Analyzer_next/execution/observer/runs/command_builder.py','Analyzer_next/adapters/observer/experiment_runtime_handoff.py','Analyzer_next/adapters/observer/cohort_search_runtime.py','Analyzer_next/execution/observer/shell2/analyze1/model.py']
    for rel in closure:
        tree=ast.parse((ROOT/rel).read_text())
        for node in ast.walk(tree):
            if isinstance(node,(ast.List,ast.Tuple)) and node.elts:
                first=node.elts[0]
                assert not (isinstance(first,ast.Constant) and first.value in {'bash','python3','python'}),rel
            if isinstance(node,ast.Call):
                assert not any(k.arg=='shell' and isinstance(k.value,ast.Constant) and k.value.value is True for k in node.keywords),rel
    checks.append('transitive known launcher closure: no Bash/hardcoded Python/shell=True')
    with tempfile.TemporaryDirectory(prefix='archon STUDIO20 spaces ') as raw:
        base=Path(raw);a=base/'portable A';b=base/'portable B'
        m=stage(ROOT,a);n=stage(ROOT,b)
        assert m==n and (a/'WINDOWS_DISTRIBUTION.json').read_bytes()==(b/'WINDOWS_DISTRIBUTION.json').read_bytes()
        checks.append('exact staging, deterministic metadata and paths with spaces')
        unexpected=b/'unlisted.tmp';unexpected.write_text('x');rejects(lambda:verify(b));unexpected.unlink()
        target=b/'ARCHON_STUDIO.sh';old=target.read_bytes();target.write_bytes(b'corrupt');rejects(lambda:verify(b));target.write_bytes(old)
        rejects(lambda:stage(ROOT,ROOT))
        bad=base/'bad.txt';bad.write_text('../escape\n');rejects(lambda:read_whitelist(bad))
        checks.append('extra bytes, modified payload, traversal and source replacement rejected')
        with patch.dict(os.environ,{'ARCHON_RUNTIME_PYTHON':str(base/'missing.exe')}):
            rejects(lambda:runtime_python_command(a))
        with patch.dict(os.environ,{'ARCHON_RUNTIME_PYTHON':sys.executable}):
            assert Path(runtime_python_command(a)[0])==Path(sys.executable).resolve()
        runtime=a/'Runtime/python'; candidate=runtime/('python.exe' if os.name=='nt' else 'bin/python3');candidate.parent.mkdir(parents=True);candidate.write_bytes(b'probe')
        with patch.dict(os.environ,{},clear=True):
            assert Path(runtime_python_command(a)[0])==candidate
        candidate.unlink()
        rejects(lambda:probe(base/'missing runtime'))
        checks.append('resolver precedence, canonical bundle location, clear missing dependency error')
        from Analyzer_next.execution.observer.shell2.analyze1.model import AnalysisLaunchPlan
        with patch.dict(os.environ,{'ARCHON_RUNTIME_PYTHON':sys.executable}):
            plan=AnalysisLaunchPlan.create(a)
        assert plan.command==(str(Path(sys.executable).resolve()),str(a/'Analyzer_next/cli/analyze_results.py'))
        checks.append('Observer Analyzer launch plan uses canonical Python command')
        output=run(a,Path('Analyzer_next/cli/observer_launcher_profile.py'),'--headless-check')
        assert json.loads(output)['production_cutover'] is True
        from Analyzer_next.execution.observer.shell2.cutover1 import CutoverService, CutoverError
        sealed=b/'Universe_Search/search_launcher.py';original=sealed.read_bytes()
        sealed.write_bytes(original+b'\n# tampered\n')
        try:
            CutoverService(b).read_profile(verify_ol2_acceptance=True)
        except CutoverError:
            pass
        else:
            raise AssertionError('Observer accepted a modified sealed source')
        finally:
            sealed.write_bytes(original)
        if os.name=='posix':
            for launcher,args in [('OBSERVER.sh',['--headless-check']),('STUDIO.sh',['--headless-smoke','--port','0']),('ARCHON_STUDIO.sh',['--headless-smoke','--port','0'])]:
                proc=subprocess.run(['bash',str(a/launcher),*args],cwd=base,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},text=True,capture_output=True,timeout=60)
                assert proc.returncode==0, launcher+': '+proc.stdout+proc.stderr
        checks.append('clean Observer production seal, tamper rejection, and actual shell entrypoints')
        # Scientific writes and all self-tests are confined to the disposable tree.
        print(run(a,Path('Tools/archon_studio_runtime.py'),'--root',a,'--self-test').strip())
        print(run(a,Path('Tools/archon_studio_desktop.py'),'--root',a,'--headless-smoke','--port','0').strip())
        snap=json.loads((a/'archon-studio/public/studio/snapshot.json').read_text())
        assert snap["mode"]=="empty_research_state" and snap["source_state"]["research_empty"]
        checks.append('bridge self-test and cold-start desktop HTTP/assets smoke')
        from archon_studio_snapshot import build_snapshot
        worlds=a/'Atlas/Worlds/atlas_index.json';worlds.parent.mkdir(parents=True,exist_ok=True)
        worlds.write_text(json.dumps([{'rule_id':'00251','world_id':'fixture-world','status':'retained'}]))
        sentinel=a/'Results/Universe_Search/existing-observation.txt';sentinel.parent.mkdir(parents=True,exist_ok=True);sentinel.write_text('existing research sentinel')
        atlas=a/'Atlas/Knowledge/research_atlas.json';atlas.parent.mkdir(parents=True,exist_ok=True)
        atlas.write_text(json.dumps({'experiments':[{'experiment_id':'EXP-fixture','rule':'00251','status':'observed','key_reasons':['Existing human-readable finding'],'is_scientific_observational':True}]}))
        knowledge=a/'Atlas/Knowledge/knowledge_base.json'
        knowledge.write_text(json.dumps({'rules':{'00251':{'validation_ids':['VAL-fixture']}},'validations':{'VAL-fixture':{'id':'VAL-fixture','evidence':['Existing observation'],'support_count':1}},'discoveries':{'DISC-fixture':{'id':'DISC-fixture','rule_id':'00251','title':'Fixture discovery','finding':'Existing human-readable finding'}}}))
        before={p:p.read_bytes() for p in [worlds,sentinel,atlas,knowledge]}
        snap=build_snapshot(a,a/'archon-studio/public/studio')
        assert '00251' in json.dumps(snap), 'existing retained world was lost'
        assert any(e['id']=='EXP-fixture' for e in snap['experiments'])
        assert any(e['id']=='VAL-fixture' for e in snap['evidence'])
        assert 'Existing human-readable finding' in json.dumps(snap['feed'])
        assert all(p.read_bytes()==data for p,data in before.items())
        checks.append('retained-world fixture detected; existing scientific bytes preserved')
        import archon_studio_runtime as rt
        from archon_studio_desktop import RuntimeSession
        bridge=rt.StudioRuntimeBridge(a)
        server=rt.StudioRuntimeHTTPServer(('127.0.0.1',0),rt.StudioRequestHandler,bridge,static_root=a/'archon-studio/dist')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        port=server.server_port;url=f'http://127.0.0.1:{port}/api/studio/health'
        try:
            with urlopen(url) as response:assert response.status==200
            for headers in [{'Origin':'https://untrusted.example'},{'Host':'untrusted.example'}]:
                try:urlopen(Request(url,headers=headers))
                except HTTPError as exc:assert exc.code==403
                else:raise AssertionError('untrusted request accepted')
            rejects(lambda:RuntimeSession(b,'127.0.0.1',port,b/'archon-studio/dist').start())
            import archon_studio_desktop as desktop
            with patch.object(desktop,'DEFAULT_PORT',port), patch.object(sys,'argv',['studio','--root',str(b),'--headless-smoke']):
                assert desktop.main()==0  # fallback from an occupied default port
            with urlopen(url) as response:assert response.status==200

            session=RuntimeSession(a,'127.0.0.1',port,a/'archon-studio/dist');session.start();assert session.attached_existing;session.close()
        finally:server.shutdown();server.server_close();thread.join()
        checks.append('loopback Host/Origin enforcement and project-specific reconnect')
    for rel in ['Tools/verify_studio18_platform_portability.py','Tools/verify_studio19_distribution_foundation.py']:
        print(run(ROOT,Path(rel)).strip())
    checks.append('unmodified STUDIO18/STUDIO19 regression assertions')
    for item in checks:print('PASS: '+item)
    print('STUDIO20 CROSS-PLATFORM PREPARATION PASS; NOT YET NATIVELY EXECUTED ON WINDOWS')

if __name__=='__main__':
    main()
