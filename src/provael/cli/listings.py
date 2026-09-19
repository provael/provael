# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The six `list-*` commands.

They read the registries and print them. Grouped together because they are the same shape and
because `provael --help` shows them as a block — splitting them across modules would put the
import list at risk of separating what a reader sees as one section."""

from __future__ import annotations

from rich.markup import escape
from rich.table import Table

from provael.attacks.registry import (
    FAMILY_STATUS_CONTROL,
    FAMILY_STATUS_FIXTURE_ONLY,
    FAMILY_STATUS_MEASURED,
    available_attacks,
    available_families,
    family_status,
    make_attack,
)
from provael.cli._shared import _POLICY_STATUS_STYLE, _out, app
from provael.defenses.registry import available_defenses, make_defense
from provael.policies.registry import (
    MEASURED_POLICIES,
    available_policies,
    policy_extra,
    policy_is_ready,
    policy_scaffolding_note,
    policy_status,
)
from provael.recipes import RECIPES, available_recipes
from provael.reproductions import available_reproductions, get_reproduction
from provael.suites import (
    KIND_FIXTURE,
    SUITE_STATUS_FIXTURE,
    SUITE_STATUS_MEASURED,
    SUITE_STATUS_UNRUN,
    available_suites,
    suite_gating_note,
    suite_is_ready,
    suite_kind,
    suite_scaffolding_note,
    suite_status,
)
from provael.suites import (
    STATUS_SCAFFOLDING as SUITE_STATUS_SCAFFOLDING,
)


@app.command("list-policies")
def list_policies() -> None:
    """List registered policies, whether they can run here, and whether they have ever been run."""
    table = Table(title="Policies")
    table.add_column("name", style="cyan", no_wrap=True)
    table.add_column("ready here", justify="center")
    # "Ready" answers "does the dependency import", which is a strictly weaker claim than "this has
    # produced a real number". Without this column all seven non-stub backends render identically,
    # and someone shopping for a `--policy` value cannot tell the one measured backend from the
    # three that have never loaded a checkpoint. An ASR from the latter measures scaffolding.
    table.add_column("status", no_wrap=True)
    table.add_column("notes")
    for name in available_policies():
        extra = policy_extra(name)
        note = escape(f"requires `provael[{extra}]` (GPU)") if extra else "CPU, no deps"
        # An importable dependency is not a run. A scaffolding backend must never render "yes"
        # here: for `groot` the advertised extra does not even provision it, so the import check
        # would be answering for a capability the install cannot deliver.
        scaffolding = policy_scaffolding_note(name)
        if scaffolding is not None:
            mark = "[yellow]no[/yellow]"
            # The `status` column already says "scaffolding"; repeating the word here only steals
            # width from the part a reader needs, which is *why* this one is scaffolding.
            why = scaffolding.removeprefix("scaffolding: ")
            note = f"{note} — {escape(why)}"
        else:
            mark = "[green]yes[/green]" if policy_is_ready(name) else "[yellow]no[/yellow]"
        status = policy_status(name)
        evidence = MEASURED_POLICIES.get(name)
        if evidence is not None:
            note = f"{note} — {escape(evidence)}"
        table.add_row(
            name, mark, f"[{_POLICY_STATUS_STYLE[status]}]{status}[/]", note
        )
    _out.print(table)
    _out.print(
        "[dim]`ready here` = the dependency imports. `status` = whether a real checkpoint has ever "
        "been run and committed. They are different questions.[/dim]"
    )


@app.command("list-suites")
def list_suites() -> None:
    """List registered suites, marking CPU fixtures apart from real simulators."""
    table = Table(title="Suites")
    table.add_column("name", style="cyan", no_wrap=True)
    table.add_column("ready here", justify="center")
    table.add_column("kind")
    # `status` answers the evidence question the other columns do not: has a committed run driven
    # a real policy through this simulator? `libero` and `metaworld` sit behind the same extra and
    # rendered identically until 20 September 2026; one holds the published body, the other has
    # never produced a committed episode (and cannot yet complete a CLI run — see its note).
    table.add_column("status")
    table.add_column("notes", min_width=24)
    for name in available_suites():
        kind = suite_kind(name)
        fixture = kind == KIND_FIXTURE
        # A fixture is deterministic arithmetic: it embodies nothing, so a rate measured on it is
        # scaffolding regardless of which policy drove it (see evidence.classify_run, which refuses
        # to label such a run `real-episode`). Saying so here is cheaper than discovering it after
        # a number has been quoted.
        # Scaffolding is checked FIRST and rendered in its own words. A registered-but-never-run
        # bridge is not "a real simulator that needs an extra" — saying so would tell a reader the
        # only thing standing between them and a measurement is a pip install.
        scaffold = suite_scaffolding_note(name)
        if scaffold is not None:
            note = escape(scaffold)
            kind = SUITE_STATUS_SCAFFOLDING
        elif fixture:
            note = "deterministic, in-process; no physics — never a real-episode measurement"
        else:
            note = escape("requires `provael[lerobot]` and a real simulator")
        gating = suite_gating_note(name)
        if gating is not None:
            note = f"{note} — {escape(gating)}"
        mark = "[green]yes[/green]" if suite_is_ready(name) else "[yellow]no[/yellow]"
        colour = "yellow" if scaffold is not None else ("cyan" if fixture else "green")
        status = suite_status(name)
        # The scaffolding label already fills the `kind` column in its long form; the status
        # column says the one word so the row does not carry the sentence twice.
        shown = "scaffolding" if status == SUITE_STATUS_SCAFFOLDING else status
        table.add_row(
            name, mark, f"[{colour}]{kind}[/]", f"[{_SUITE_STATUS_STYLE[status]}]{shown}[/]", note
        )
    _out.print(table)
    _out.print(
        "[dim]A CPU fixture is reproducible scaffolding, not evidence about a robot. Only a real "
        "simulator produces a `real-episode` run; `status` says whether one has been committed "
        "through this suite.[/dim]"
    )



_SUITE_STATUS_STYLE: dict[str, str] = {
    SUITE_STATUS_MEASURED: "green",
    SUITE_STATUS_FIXTURE: "cyan",
    SUITE_STATUS_SCAFFOLDING: "yellow",
    SUITE_STATUS_UNRUN: "yellow",
}

_FAMILY_STATUS_STYLE: dict[str, str] = {
    FAMILY_STATUS_MEASURED: "green",
    FAMILY_STATUS_FIXTURE_ONLY: "yellow",
    FAMILY_STATUS_CONTROL: "dim",
}

@app.command("list-attacks")
def list_attacks() -> None:
    """List registered attacks and attack families."""
    table = Table(title="Attacks")
    table.add_column("attack", style="cyan", no_wrap=True)
    table.add_column("family", style="magenta")
    # Per FAMILY, because the evidence is per family: `measured` = a committed run drove this
    # family against a real policy in a real simulator (the run README carries the rate, which may
    # be a null); `fixture-only` = only the deterministic CPU fixture has ever seen it, and every
    # rate it has produced is a property of a fixture written to be attackable; `control` = not
    # an attack. `full-sweep` on a real policy runs the measured ones by default.
    table.add_column("status", no_wrap=True)
    for name in available_attacks():
        family = make_attack(name).family
        status = family_status(family)
        table.add_row(name, family, f"[{_FAMILY_STATUS_STYLE[status]}]{status}[/]")
    _out.print(table)
    _out.print(f"families: {', '.join(available_families())}")
    _out.print(
        "[dim]`status` is per family: measured = a committed real-policy run (rate or null, see "
        "the run README); fixture-only = only the CPU fixture has ever seen it; control = not an "
        "attack. `attack --recipe full-sweep` on a real policy runs the measured families unless "
        "--include-fixture-families is passed.[/dim]"
    )


@app.command("list-recipes")
def list_recipes() -> None:
    """List built-in run recipes (named RunConfig presets for `attack --recipe`)."""
    table = Table(title="Recipes")
    table.add_column("recipe", style="cyan", no_wrap=True)
    table.add_column("attacks", style="magenta")
    table.add_column("episodes", justify="right")
    table.add_column("description")
    for name in available_recipes():
        cfg = RECIPES[name].config
        attacks = ", ".join(cfg.get("attacks", ["instruction"]))
        episodes = str(cfg.get("episodes", 10))
        table.add_row(name, attacks, episodes, RECIPES[name].description)
    _out.print(table)
    _out.print("Use: [cyan]provael attack --recipe <name>[/cyan]  (explicit flags override it)")


@app.command("list-reproductions")
def list_reproductions() -> None:
    """List published-attack reproductions (`reproduce <name>`)."""
    table = Table(title="Reproductions")
    table.add_column("name", style="cyan", no_wrap=True)
    table.add_column("EAI", style="magenta")
    table.add_column("paper")
    table.add_column("Provael family")
    for name in available_reproductions():
        repro = get_reproduction(name)
        table.add_row(name, repro.eai, f"{repro.title.split(':')[0]} ({repro.arxiv})",
                      ", ".join(repro.attacks))
    _out.print(table)
    _out.print("Use: [cyan]provael reproduce <name>[/cyan]  (defaults to the CPU stub)")


@app.command("list-defenses")
def list_defenses() -> None:
    """List registered defenses (mitigations measured under the docs/defenses.md protocol)."""
    table = Table(title="Defenses")
    table.add_column("defense", style="cyan", no_wrap=True)
    table.add_column("kind", style="magenta")
    # A certifier reading "a defense was applied" needs to know whether it was a text pre-filter or
    # an output monitor: different protective measures, different failure modes.
    table.add_column("position")
    table.add_column("EAI ids")
    table.add_column("status")
    for name in available_defenses():
        d = make_defense(name)
        # "measured" ONLY where a study exists — docs/defenses.md keeps every other taxonomy row at
        # "specified, unproven" and this column must not quietly upgrade one.
        #
        # Read from the class attribute, NOT from the filesystem. Probing for
        # docs/studies/<name>.md worked in a git checkout and never in an installed wheel (docs/ is
        # not packaged), so 0.26.0 told every user its one measured defense was unproven.
        status = "measured" if d.study else "specified, unproven"
        table.add_row(name, d.kind, d.position, ", ".join(d.eai_ids) or "—", status)
    _out.print(table)
    _out.print(
        "Four of the six docs/defenses.md taxonomy rows ship no implementation and are "
        "deliberately absent: an unmeasured mitigation is not a registered one."
    )
    _out.print(
        "Use: [cyan]provael attack --defense <name>[/cyan] then [cyan]provael mitigation[/cyan]"
    )
