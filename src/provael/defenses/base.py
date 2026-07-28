"""Defense interface — the mitigation counterpart to :class:`~provael.attacks.base.Attack`.

A :class:`Defense` is a **pre-processing wrapper** applied to the ``(instruction, observation)``
pair on its way into the policy. ``docs/DEFENSES.md`` states the contract this ABC exists to
enforce: the pipeline "runs as a pre-processing wrapper on the instruction; it changes no policy
weights and is auditable (the canonical form is logged next to the raw instruction)".

That sentence carries three constraints, and the shape of this class is how they are held:

**It cannot touch the policy.** :meth:`apply` is handed an instruction and an observation and must
return an instruction and an observation. It is never given the policy, the suite, the report, or
the attack — so a "defense" that lowers ASR by reaching into the model, the scorer, or the danger
predicate cannot be written against this interface at all. A mitigation that needs policy weights
is a different kind of artifact and does not belong here.

**It must be auditable.** :meth:`audit` returns the raw → canonical trail for one instruction,
which the runner writes to a ``defense-log.jsonl`` sidecar. A certifier reading a mitigation report
can therefore see exactly what the defense did to each instruction, not merely that the number
moved.

**It must not be able to win by cheating.** A defense that deletes the operator's task would drop
ASR to zero and look excellent. ``provael.scoring.asr.is_command_preserving`` — the same honesty
gate the redirection *search* is held to — is applied to the canonicaliser's own output in
``tests/test_defenses.py``, and the measurement layer
(:mod:`provael.defenses.measure`) additionally enforces a benign-task-success acceptance gate.

Determinism is inherited from the runner's contract: a report is a pure function of its config, so
:meth:`apply` must be deterministic and must not consult a clock, the network, or unseeded
randomness.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from provael.types import Observation


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

    def audit(self, instruction: str) -> dict[str, str]:
        """The raw → canonical trail for one instruction, for the ``defense-log.jsonl`` sidecar.

        Default records only the raw and defended forms. A defense with intermediate stages should
        override and name each one, because "the number moved" is not evidence — *what changed* is.
        Returns plain ``str -> str`` so the sidecar stays greppable and diffable.
        """
        defended, _ = self.apply(instruction, {})
        return {"raw": instruction, "canonical": defended}


__all__ = ["Defense"]
