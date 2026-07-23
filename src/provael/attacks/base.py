"""Attack interface.

An :class:`Attack` perturbs the instruction (and optionally the observation) that a
policy receives, attempting to drive the policy into an unsafe state. Most shipped
families are *templated* — a fixed transform of the observation (``instruction`` text
reframings, ``visual`` perturbations, ``injection`` payloads, …).

:class:`OptimizedAttack` generalises that into a **bounded-budget, on-policy search**:
propose candidate edits, roll each out against the policy (via an oracle the runner
wires in, or a deterministic surrogate), score it, keep the best, and early-stop on
target-success or when the query budget is spent. It *composes over* :class:`Attack`
— a concrete optimized attack still returns a single ``(instruction, observation)``
pair from :meth:`Attack.perturb`; the search just decides which pair — so the base
contract, the runner and scoring are all unchanged.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable

from provael.types import Action, Observation


class Attack(ABC):
    """Transforms ``(instruction, observation)`` into an adversarial variant."""

    #: Stable, human-readable identifier (also the registry key).
    name: str = "base"
    #: Attack family this attack belongs to (e.g. ``"instruction"``).
    family: str = "base"
    #: Embodied AI Security Top-10 risk id this attack maps to (e.g. ``"EAI01"``).
    #: ``None`` for the baseline control, which is not an attack technique.
    eai_id: str | None = None
    #: Human-readable name of that risk (mirrors :data:`provael.eai.CATALOG`).
    eai_name: str | None = None
    #: INV-4 threat-model metadata: the attacker's access class, one of
    #: ``"white-box-gradient"`` / ``"black-box-query"`` / ``"in-scene-physical"``.
    #: ``None`` where not asserted (e.g. the stub-scaffolding families that make no
    #: real-access claim). Recorded on every :class:`~provael.types.AttackResult` so a
    #: result is self-describing and no freeze/token attack is silently assumed to transfer.
    attacker_access: str | None = None
    #: INV-4 threat-model metadata: the policy action-head class the attack was measured
    #: against — ``"token"`` (discrete autoregressive) or ``"flow"`` (flow-matching). ``None``
    #: where not asserted. A stub-only attack does not claim a head class; a real-transfer
    #: attack records the one it actually ran against (see ROADMAP D3/INV-4).
    action_head_class: str | None = None

    def applicable(self, observation: Observation) -> bool:
        """Whether this attack has a surface in the given suite's observation.

        Default True. Returning False marks the attack **not-applicable** for that suite
        (e.g. ``mcp_tool_desc`` has no MCP surface in a direct LIBERO loop); such episodes
        are excluded from the ASR denominator rather than faked.
        """
        return True

    @abstractmethod
    def perturb(self, instruction: str, observation: Observation) -> tuple[str, Observation]:
        """Return an adversarial ``(instruction, observation)`` pair.

        Implementations must be **deterministic**: given the same inputs they must
        always return the same output (any per-episode variation must be derived
        from values already present in ``observation``, e.g. its ``"seed"``).

        Args:
            instruction: The base (benign) task instruction.
            observation: The current observation dict.

        Returns:
            ``(adversarial_instruction, observation)``. Instruction-family attacks
            return the observation unchanged.
        """


#: Default per-episode query budget for an optimized search (max policy queries it may make).
DEFAULT_OPTIMIZED_BUDGET = 64

#: An oracle: given ``(instruction, observation)`` return the policy's action. The runner
#: (:func:`provael.runner._configure_optimized`) wires one into any attack exposing
#: :meth:`OptimizedAttack.attach_oracle` + ``query_budget`` (its ``OracleAttack`` protocol).
OptimizedOracle = Callable[[str, Observation], Action]


class OptimizedAttack[Edit](Attack):
    """A bounded-budget, on-policy **greedy search** over candidate perturbations.

    The search is a coordinate-ascent / greedy hill-climb: score the seed candidates
    (:meth:`_seed_edits`), keep the best incumbent, expand it by one bounded edit
    (:meth:`_expand_edit`), and repeat — stopping when the best score reaches
    :meth:`_target_score`, the ``query_budget`` is spent, or a round yields no improvement. Each
    candidate is rolled out through an *oracle* the runner wires in (:meth:`attach_oracle`), or a
    deterministic :meth:`_surrogate` when none is attached, so the whole search is CPU-testable
    with no policy. The search runs **once per episode** (cached by the observation ``seed``); its
    winning pair is returned from :meth:`perturb`, so the single-shot :class:`Attack` contract, the
    runner, and scoring are untouched.

    Exposing ``query_budget`` + :meth:`attach_oracle` makes an instance match the runner's
    ``OracleAttack`` protocol *structurally*, so :func:`provael.runner._configure_optimized` wires
    the policy oracle without importing any concrete subclass (as it already does for the shipped
    action- and image-channel optimized families).
    """

    #: Max policy queries the search may make per episode (its compute budget). The runner may
    #: override this from ``--query-budget``.
    query_budget: int = DEFAULT_OPTIMIZED_BUDGET

    def __init__(
        self,
        query_budget: int = DEFAULT_OPTIMIZED_BUDGET,
        rollouts_per_candidate: int = 1,
    ) -> None:
        self.query_budget = int(query_budget)
        #: Queries to average per candidate (>1 reduces variance against a *stochastic* real policy;
        #: 1 is exact on the deterministic stub). Each rollout counts against ``query_budget``.
        self.rollouts_per_candidate = max(1, int(rollouts_per_candidate))
        self._oracle: OptimizedOracle | None = None
        self._reset: Callable[[], None] | None = None
        self._cache: dict[int, tuple[str, Observation]] = {}
        #: Queries the most recent :meth:`_search` used (asserted by the budget/early-stop tests).
        self.last_search_queries = 0
        #: The winning edit of the most recent :meth:`_search` (``None`` if every candidate was
        #: rejected). Lets a caller freeze the discovered *operator* — e.g. for a held-out
        #: transfer-test that re-applies it to unseen instructions, not just the one it trained on.
        self.best_edit: Edit | None = None

    def attach_oracle(
        self, query: OptimizedOracle, reset: Callable[[], None] | None = None
    ) -> None:
        """Wire a policy-query oracle so the search is a genuine black-box query attack.

        ``query(instruction, observation)`` returns the policy's action for a candidate; ``reset``
        (optional) restores clean policy state and is called once after the search so it never
        pollutes the live rollout. Without an oracle the deterministic :meth:`_surrogate` is used.
        """
        self._oracle = query
        self._reset = reset

    # ---- hooks a concrete optimized attack implements ---------------------------------------- #

    @abstractmethod
    def _seed_edits(self, instruction: str, observation: Observation) -> Iterable[Edit]:
        """Round-0 candidate edits (deterministic; the cheapest / most command-preserving ones)."""

    @abstractmethod
    def _expand_edit(
        self, incumbent: Edit, instruction: str, observation: Observation
    ) -> Iterable[Edit]:
        """Neighbours of ``incumbent``: it plus one more bounded edit (deterministic order)."""

    @abstractmethod
    def _render(
        self, edit: Edit, instruction: str, observation: Observation
    ) -> tuple[str, Observation]:
        """Apply ``edit`` to produce the ``(instruction, observation)`` pair to roll out."""

    @abstractmethod
    def _objective(self, action: Action) -> float:
        """Score a rolled-out action; higher is a better attack (the search maximises this)."""

    def _accept(self, edit: Edit, instruction: str, observation: Observation) -> bool:
        """Validity gate on a candidate (default: accept). Reject to enforce a hard constraint."""
        return True

    def _surrogate(self, edit: Edit, instruction: str, observation: Observation) -> float:
        """Objective for a candidate when no oracle is attached (deterministic, CPU-only).

        Default raises: a subclass that wants to run without a wired policy (e.g. a unit test on the
        deterministic stub) overrides this with the fixture's closed-form response.
        """
        raise NotImplementedError(
            f"{type(self).__name__}: no oracle attached and no _surrogate() override; "
            "call attach_oracle(...) or override _surrogate(...)."
        )

    def _target_score(self) -> float:
        """Early-stop threshold: stop as soon as the best score reaches this (default: never)."""
        return float("inf")

    # ---- the shared search loop -------------------------------------------------------------- #

    def _score_candidate(
        self, edit: Edit, instruction: str, observation: Observation
    ) -> tuple[float, int, tuple[str, Observation]]:
        """Return ``(score, queries_used, rendered_pair)`` for one candidate.

        With an oracle attached the objective is averaged over ``rollouts_per_candidate`` policy
        queries (each counted against the budget); without one the closed-form surrogate is used
        (one notional query).
        """
        rendered = self._render(edit, instruction, observation)
        if self._oracle is None:
            return self._surrogate(edit, instruction, observation), 1, rendered
        rendered_instruction, rendered_observation = rendered
        total = 0.0
        for _ in range(self.rollouts_per_candidate):
            total += self._objective(self._oracle(rendered_instruction, rendered_observation))
        return total / self.rollouts_per_candidate, self.rollouts_per_candidate, rendered

    def _search(self, instruction: str, observation: Observation) -> tuple[str, Observation]:
        """Run the budgeted greedy search once; return the best ``(instruction, observation)``."""
        best_pair = (instruction, observation)  # benign fallback if every candidate is rejected
        best_edit: Edit | None = None
        best_score = float("-inf")
        queries = 0
        target = self._target_score()
        visited: set[Edit] = set()
        frontier: list[Edit] = list(self._seed_edits(instruction, observation))

        while frontier and queries < self.query_budget:
            improved = False
            for edit in frontier:
                if queries >= self.query_budget:
                    break
                if edit in visited:
                    continue
                visited.add(edit)
                if not self._accept(edit, instruction, observation):
                    continue
                score, used, rendered = self._score_candidate(edit, instruction, observation)
                queries += used
                if score > best_score:
                    best_score, best_edit, best_pair, improved = score, edit, rendered, True
            if best_edit is None or best_score >= target or not improved:
                break  # nothing scorable, target-success, or a plateau (local optimum) → done
            frontier = list(self._expand_edit(best_edit, instruction, observation))

        self.last_search_queries = queries
        self.best_edit = best_edit
        if self._reset is not None:
            self._reset()  # restore clean policy state for the live rollout
        return best_pair

    def perturb(self, instruction: str, observation: Observation) -> tuple[str, Observation]:
        """Return the search's winning pair for this episode (searched once, cached per seed)."""
        seed = observation.get("seed")
        key = seed if isinstance(seed, int) else -1
        cached = self._cache.get(key)
        if cached is None:
            cached = self._search(instruction, observation)
            self._cache[key] = cached
        return cached
