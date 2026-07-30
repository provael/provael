"""Defense interface — the mitigation counterpart to :class:`~provael.attacks.base.Attack`.

A :class:`Defense` wraps the policy from **both sides**: :meth:`Defense.apply` pre-processes the
``(instruction, observation)`` pair on its way in, and :meth:`Defense.filter_action` inspects the
commanded action on its way out. ``docs/DEFENSES.md`` states the contract this ABC exists to
enforce: the pipeline "runs as a pre-processing wrapper on the instruction; it changes no policy
weights and is auditable (the canonical form is logged next to the raw instruction)".

**Why there are two hooks.** The taxonomy in ``docs/DEFENSES.md`` lists six mitigation rows, and
four of them — action clamping / keep-out enforcement, trajectory anomaly detection, rate limiting /
scope enforcement, and output / memory screening — act on what comes *out* of the policy, not on
what goes in. With only a pre-processing hook those four could not be written against this
interface at all: the taxonomy was a spec its own interface could not satisfy. :meth:`filter_action`
closes that gap. It is **not abstract** and defaults to the identity, so an input-side defense such
as :class:`~provael.defenses.canonicalize.InstructionCanonicalization` and any third-party defense
written against the older interface keep working untouched.

The three constraints below are the reason this class has the shape it has, and they bind
:meth:`filter_action` exactly as they bind :meth:`apply`:

**It cannot touch the policy.** :meth:`apply` is handed an instruction and an observation and must
return an instruction and an observation. :meth:`filter_action` is handed an action and an
observation and must return an action. Neither is ever given the policy, the suite, the report, the
attack, the task id, or the danger predicate — so a "defense" that lowers ASR by reaching into the
model, the scorer, or the unsafe threshold cannot be written against this interface at all. A
mitigation that needs policy weights is a different kind of artifact and does not belong here.

This bites hardest on the action side, and deliberately. Every CPU suite decides "unsafe" by
comparing a channel of the commanded action against a bound it owns
(``provael.suites.stub.THRESHOLD_LO``, ``provael.suites.reach.KEEP_OUT_X_MIN``). A clamp that
imported one of those constants would score 0% ASR *by construction* and would have measured
nothing at all. Because the hook never receives the suite, such a defense has to reach for an
import — which is a visible, testable act, and ``tests/test_defenses.py`` asserts against it.

**It must be auditable.** :meth:`audit` returns the raw → canonical trail for one instruction and
:meth:`audit_action` the raw → filtered trail for one action; the runner writes both to the same
``defense-log.jsonl`` sidecar. A certifier reading a mitigation report can therefore see exactly
what the defense did to each instruction and each action, not merely that the number moved. "The
number moved" is not evidence — *what changed* is.

**It must not be able to win by cheating.** A defense that deletes the operator's task would drop
ASR to zero and look excellent. ``provael.scoring.asr.is_command_preserving`` — the same honesty
gate the redirection *search* is held to — is applied to the canonicaliser's own output in
``tests/test_defenses.py``, and the measurement layer
(:mod:`provael.defenses.measure`) additionally enforces a benign-task-success acceptance gate.

Determinism is inherited from the runner's contract: a report is a pure function of its config, so
:meth:`apply` and :meth:`filter_action` must be deterministic and must not consult a clock, the
network, or unseeded randomness.

**Nothing here adds a field to** :class:`~provael.types.RunReport`. The action-side hook was the
obvious excuse to record a filtered action on ``AttackResult``, and that is exactly where it must
not go: ``AttackResult`` is nested in ``RunReport.results``, so a field there moves the canonical
JSON the attestation is signed over and every attestation issued by an earlier version stops
verifying. The action trail lives in the sidecar and the position metadata lives on the mitigation
report. ``tests/test_defenses.py`` asserts the ``RunReport`` field set is unchanged.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from provael.types import Action, Observation


class Defense(ABC):
    """Transforms ``(instruction, observation)`` into a defended variant, before the policy sees it.

    Applied by the runner strictly *between* the attack's perturbation and ``policy.act`` — the
    deployment position a real operator would install it in, so what is measured is what would
    ship.
    """

    #: Stable, human-readable identifier (also the registry key).
    name: str = "base"
    #: Taxonomy row from ``docs/DEFENSES.md`` (e.g. ``"input-canonicalization"``). Kept as free
    #: text rather than an enum because the taxonomy is a document the reader can check, and a
    #: mitigation whose row is not yet written should be able to say so.
    kind: str = "base"
    #: Embodied AI Security Top-10 risk ids this mitigation primarily addresses. Empty means the
    #: defense makes no coverage claim — the honest default for a scaffold.
    eai_ids: tuple[str, ...] = ()
    #: Where in the pipeline this defense acts: ``"input"``, ``"action"``, or ``"input+action"``.
    #:
    #: This is not bookkeeping. A mitigation report is filed as conformity evidence, and a certifier
    #: reading "a defense was applied" needs to know whether it was a text pre-filter or an output
    #: monitor — those are different protective measures with different failure modes. A text filter
    #: fails open when an attacker rephrases below its lexicon; an output clamp fails open when the
    #: hazard is reachable inside the envelope, and can itself *cause* a hazard by clipping a
    #: command the task needed. Collapsing the two into "defended" would make the dossier
    #: unreadable in precisely the way ISO 10218-2:2025's "precise description of safety-relevant
    #: functions"
    #: exists to prevent. Defaults to ``"input"`` — the position every defense that predates this
    #: attribute actually occupied.
    position: str = "input"
    #: Path of the published study measuring this defense, relative to the repo root, or ``None``
    #: for one that has not been measured. ``None`` is the default, so a new defense is *unproven*
    #: until someone sets this — the same direction of failure as an empty ``eai_ids``.
    #:
    #: DATA, NOT A FILESYSTEM PROBE. ``provael list-defenses`` first decided "measured" by checking
    #: whether ``docs/studies/<name>.md`` existed on disk. That worked in a git checkout and never
    #: in an installed wheel, because ``docs/`` is not packaged — so 0.26.0 shipped telling every
    #: user that its one measured defense was "specified, unproven", the tool contradicting its own
    #: published study. A class attribute travels with the code.
    study: str | None = None

    def applicable(self, observation: Observation) -> bool:
        """Whether this defense has a surface in the given suite's observation.

        Default True. Mirrors :meth:`provael.attacks.base.Attack.applicable` so a defense that
        cannot act on a suite is a no-op rather than a silent partial application.
        """
        return True

    @abstractmethod
    def apply(self, instruction: str, observation: Observation) -> tuple[str, Observation]:
        """Return the defended ``(instruction, observation)`` pair.

        Implementations must be **deterministic** and must not mutate ``observation`` in place —
        return a new mapping if the observation changes at all.

        Args:
            instruction: The instruction as the policy would otherwise receive it (i.e. already
                perturbed by the attack, since the defense sits in the deployment position).
            observation: The current observation dict.

        Returns:
            The ``(instruction, observation)`` pair to hand to the policy.
        """

    def filter_action(self, action: Action, observation: Observation) -> Action:
        """Inspect the commanded action on its way out of the policy; return the action to execute.

        Default is the identity, so an input-side defense needs no changes and neither does any
        third-party defense written before this hook existed.

        Implementations get the **action and the observation and nothing else** — never the policy,
        the suite, the report, the attack, the task id, or the unsafe predicate. That is what stops
        a clamp from being tuned against the bound it is measured on; see the module docstring.

        Must be **deterministic**, and must **not mutate ``action`` in place**: return a new array.
        The runner records the raw policy output and hands the raw array here, so mutating it would
        silently rewrite what the report says the policy commanded.

        Args:
            action: The raw action as the policy emitted it, already checked for non-finite values.
            observation: The observation the policy acted on.

        Returns:
            The action to hand to the suite.
        """
        return action

    def audit(self, instruction: str) -> dict[str, str]:
        """The raw → canonical trail for one instruction, for the ``defense-log.jsonl`` sidecar.

        Default records only the raw and defended forms. A defense with intermediate stages should
        override and name each one, because "the number moved" is not evidence — *what changed* is.
        Returns plain ``str -> str`` so the sidecar stays greppable and diffable.
        """
        defended, _ = self.apply(instruction, {})
        return {"raw": instruction, "canonical": defended}

    def audit_action(self, raw: Action, filtered: Action) -> dict[str, str]:
        """The raw → filtered trail for one action, for the same ``defense-log.jsonl`` sidecar.

        Default records both vectors and whether anything changed. A clamp should override to name
        *which* channel it bound and by how much: an operator reviewing a credited action-side
        result needs to see that the envelope engaged on the danger channel and left the task motion
        alone, not merely that the ASR fell.

        Returns plain ``str -> str`` like :meth:`audit`, so one sidecar holds both kinds of row and
        stays greppable and diffable at any run size.
        """
        raw_arr = np.asarray(raw, dtype=np.float32).reshape(-1)
        new_arr = np.asarray(filtered, dtype=np.float32).reshape(-1)
        altered = raw_arr.shape != new_arr.shape or not bool(np.array_equal(raw_arr, new_arr))
        return {
            "raw_action": np.array2string(
                raw_arr, precision=6, separator=",", max_line_width=10**6
            ),
            "filtered_action": np.array2string(
                new_arr, precision=6, separator=",", max_line_width=10**6
            ),
            "action_altered": "true" if altered else "false",
        }


__all__ = ["Defense"]
