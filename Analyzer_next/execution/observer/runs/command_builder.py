"""CommandBuilder responsibilities."""
from __future__ import annotations

from Tools.archon_runtime_python import runtime_python_command

from ..settings import *
from ..catalog import *


class CommandBuilderMixin:
    def _common_flags(
        self,
        *,
        max_ticks_override: int | None = None,
        sample_every_override: int | None = None,
        pressure_every_override: int | None = None,
        force_no_auto_stop: bool = False,
        force_samples: bool = False,
        force_passport: bool = False,
    ) -> list[str]:
        max_ticks = (
            int(max_ticks_override)
            if max_ticks_override is not None
            else int(self.max_ticks_var.get())
        )
        flags = [
            "--cell", str(self.cell_var.get()),
            "--speed", str(self.speed_var.get()),
            "--delay", str(self.delay_var.get()),
            "--autosave-every", str(self.autosave_var.get()),
            "--sample-every", str(
                sample_every_override
                if sample_every_override is not None
                else self.sample_every_var.get()
            ),
            "--pressure-timeline-every",
            str(
                pressure_every_override
                if pressure_every_override is not None
                else self.pressure_every_var.get()
            ),
        ]
        if max_ticks > 0:
            flags.extend(["--max-ticks", str(max_ticks)])
        if self.auto_stop_var.get() and not force_no_auto_stop:
            flags.append("--auto-stop")
        if self.samples_var.get() or force_samples:
            flags.append("--samples-csv")
        if self.events_var.get():
            flags.append("--events-csv")
        if self.pressure_var.get():
            flags.append("--pressure-timeline-csv")
        if self.chronicle_var.get():
            flags.append("--chronicle-csv")
        if self.passport_var.get() or force_passport:
            flags.append("--passport")
        if self.log_var.get():
            flags.append("--log")
        flags.append(
            "--telemetry-sqlite"
            if self.sqlite_var.get()
            else "--no-telemetry-sqlite"
        )
        flags.append(
            "--evidence-framework"
            if self.evidence_var.get()
            else "--no-evidence-framework"
        )
        return flags

    def _base_command(
        self,
        run: dict[str, Any] | None = None,
    ) -> list[str]:
        selector = normalize_rule_id(
            run.get("rule_id")
            if run is not None and run.get("rule_id") is not None
            else self.rule_var.get()
        )
        is_mutation = run is not None and run.get("rule_file") is not None
        is_experimental_mutation = (
            is_mutation
            and run is not None
            and run.get("mode") == "experimental_mutation"
        )
        is_control = (
            run is not None
            and run.get("mode") == "required_control"
        )
        cmd = [
            *runtime_python_command(PROJECT_ROOT),
            str(OBSERVER_SCRIPT),
            str(SEARCH_RESULTS_DIR),
            selector,
            *self._common_flags(
                max_ticks_override=(
                    run.get("max_ticks_override")
                    if is_experimental_mutation and run is not None
                    else 0 if is_mutation
                    else run.get("max_ticks_override")
                    if run is not None else None
                ),
                sample_every_override=(
                    run.get("sample_every_override")
                    if run is not None else None
                ),
                pressure_every_override=(
                    run.get("pressure_every_override")
                    if run is not None else None
                ),
                force_no_auto_stop=is_mutation or is_control,
                force_samples=is_control,
                force_passport=is_control,
            ),
        ]
        if run is not None and run.get("run_output_dir") is not None:
            cmd.extend([
                "--run-output-dir", str(run["run_output_dir"]),
            ])
        elif is_mutation:
            cmd.extend([
                "--run-output-dir", str(run["run_dir"]),
            ])
        if is_mutation:
            cmd.extend([
                "--rule-file", str(run["rule_file"]),
                "--mutation-manifest", str(run["manifest_file"]),
            ])

        if (
            run is not None
            and run.get("mode") in {
                "experiment_plan",
                "production_experiment_plan",
                "experimental_mutation",
                "canonical_queue",
                "canonical_backlog",
            }
        ):
            cmd.append("--exit-at-max-ticks")

        experiment_context = (
            run.get("experimental_context")
            if run is not None
            else self._selected_experimental_context()
        )
        if experiment_context is not None:
            cmd.extend([
                "--experiment-id",
                str(experiment_context["experiment_id"]),
                "--condition-id",
                str(experiment_context["condition_id"]),
                "--experiment-role",
                str(experiment_context["role"]),
                "--replicate-index",
                str(experiment_context["replicate_index"]),
                "--field-width",
                str(experiment_context["field_width"]),
                "--field-height",
                str(experiment_context["field_height"]),
                "--topology",
                str(experiment_context["topology"]),
                "--boundary-mode",
                str(experiment_context["boundary_mode"]),
                "--initial-state-mode",
                str(experiment_context["initial_state_mode"]),
            ])
            if experiment_context.get("seed") is not None:
                cmd.extend([
                    "--experiment-seed",
                    str(experiment_context["seed"]),
                ])
            if experiment_context.get("treatment_arm"):
                cmd.extend([
                    "--treatment-arm",
                    str(experiment_context["treatment_arm"]),
                ])
        return cmd

    def _update_command_preview(self) -> None:
        try:
            self.command_var.set(
                shlex.join(self._base_command())
            )
        except Exception:
            self.command_var.set(
                "Select a rule to build the Observer command."
            )
