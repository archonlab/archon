#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from Analyzer_next.core.metric_independence.audit import build_report,render_markdown
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("profiles");p.add_argument("--out",required=True);p.add_argument("--md-out");a=p.parse_args(argv)
 profile=Path(a.profiles).expanduser().resolve()
 try: payload=json.loads(profile.read_text(encoding="utf-8")); payload=payload if isinstance(payload,dict) else {}
 except (OSError,json.JSONDecodeError):payload={}
 report=build_report(payload,str(profile),datetime.now(timezone.utc).isoformat());out=Path(a.out).expanduser().resolve();out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
 if a.md_out: md=Path(a.md_out).expanduser().resolve();md.parent.mkdir(parents=True,exist_ok=True);md.write_text(render_markdown(report),encoding="utf-8")
 print(f"[metric-audit] status={report['status']} profiles={report['profile_count']} v2={report['empirical_diagnostics']['independent_v2_profile_count']}");return 0
if __name__=="__main__":raise SystemExit(main())
