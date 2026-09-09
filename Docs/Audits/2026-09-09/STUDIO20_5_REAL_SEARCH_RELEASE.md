# STUDIO20.5 real Universe Search release audit

## Finding

The source and packaged Studio frontend both request the embedded Search endpoint,
and `StudioRuntimeBridge` builds a child-process command for
`Universe_Search/universe_search_v34_closed_research_cycle.py`. Search Launcher
also starts that entrypoint. There is no separate scientific Search
implementation in the production browser bundle.

The release defect was in verification and failure semantics: staging tests
checked that a few entrypoints existed and that the command looked plausible,
but never executed a generation from a clean release. Studio also accepted exit
code zero as success without proving that the canonical process had emitted any
runtime lifecycle telemetry or committed a real generation artifact. That left
an incomplete or incorrectly assembled release indistinguishable from convincing
presentation-only activity.

## Fix

- `Universe_Search/search_runtime_contract.py` is the shared launch and closure
  contract used by Studio and Search Launcher.
- Production launch validates the complete canonical Search module set and fails
  visibly when it is incomplete. There is no demo fallback.
- The canonical engine emits structured, PID-bound operational events for process
  start, generation commit, and completion. These events do not change scoring,
  mutation, selection, or any other scientific operation.
- Studio ignores human-readable progress until the real child process attests its
  PID. A generation commit is accepted only after its JSON result file is read
  and validated under `Results/Universe_Search`.
- An embedded Search cannot finish successfully in Studio without the matching
  canonical start and completion attestations.

## Release regression

`Tools/verify_studio_real_search_release.py` builds a fresh exact release stage,
adds a normal one-candidate checkpoint at generation 7, and resumes through the
Studio bridge. The unmodified canonical Search entrypoint executes generation 8.
The test proves the child PID, telemetry/PID correspondence, real evaluation
progress, canonical checkpoint and Atlas integration, and a genuine run-scoped
generation result containing rule and metrics objects.

The compact checkpoint keeps the release regression bounded; it does not patch
the Search code or alter scientific constants.

## Scientific semantics

Universe Search scoring, evaluation, selection, mutation, and persistence are
unchanged. Observer, Analyzer, and Experiment semantics are unchanged. The
change is limited to launch closure, operational telemetry, and release
verification.
