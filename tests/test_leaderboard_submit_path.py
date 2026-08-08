"""The submission funnel must never report a capture that did not happen.

WHY THIS EXISTS. `leaderboard/app.py` pointed its submit button at the Hugging Face dataset
`provael-submissions/requests`, which has never existed — verified 2026-08-08: the org page returns
404, the datasets API returns 401, `?author=provael-submissions` returns `[]`. The call to
`upload_file` had no error handling, so the first outsider to press Submit would have been handed a
raw Gradio traceback.

It survived because the leaderboard has had ZERO third-party submissions in its lifetime. The one
path a stranger takes to contribute had never been walked by a stranger, so nothing exercised it.
That is precisely the condition under which a funnel rots invisibly, and it is why the fix is a test
rather than a fixed string: the repo cannot rely on someone trying it.

The rule these tests pin is the same one the website's lead-sink chain was rebuilt twice to enforce:
report success only on evidence, and always leave a route that works.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

APP = Path(__file__).resolve().parent.parent / "leaderboard" / "app.py"


def _app() -> Any:
    """Import the Space module by path, with `gradio` stubbed.

    Deliberately NOT `pytest.importorskip("gradio")`. gradio is not in the CPU dev group and adding
    it would put a large UI dependency into the lane whose whole point is staying light — so the
    skip would fire on every CI run, and a test that always skips guards nothing. That is the same
    "passes for the wrong reason" failure this file exists to catch, one level up.

    The stub is sound because `submit_result` touches no gradio API; gradio is imported at module
    scope and used only when the UI is built.
    """
    for name in ("gradio", "huggingface_hub"):
        # huggingface_hub is likewise absent from the CPU lane. submit_result imports it lazily
        # inside the function, so a stub here is what the monkeypatched HfApi attaches to.
        if name not in sys.modules:
            stub = ModuleType(name)
            stub.__getattr__ = lambda _n: MagicMock()  # type: ignore[attr-defined]
            sys.modules[name] = stub
    spec = importlib.util.spec_from_file_location("provael_space_app", APP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["provael_space_app"] = module
    spec.loader.exec_module(module)
    return module


def test_a_failed_upload_says_not_submitted_and_gives_a_working_route(monkeypatch: Any) -> None:
    """The live failure mode: the target dataset does not exist, so the upload raises."""
    app = _app()
    monkeypatch.setenv("HF_TOKEN", "fake-token-for-the-error-path")

    class Boom:
        def __init__(self, *a: Any, **k: Any) -> None: ...
        def upload_file(self, **kwargs: Any) -> Any:
            raise RuntimeError("404 Client Error: Repository Not Found")

    monkeypatch.setattr("huggingface_hub.HfApi", Boom)
    out = app.submit_result("someorg/their-vla", str(APP))

    assert "Not submitted" in out, out
    assert "Submitted —" not in out, "a failed upload reported success"
    # The submitter must be told their result is NOT queued, in words, not implied by a stack trace.
    assert "not queued" in out.lower(), out
    # And handed a route that needs no HF org, no token and no dataset to exist.
    assert app.GUARANTEED_ROUTE in out, out


def test_success_is_only_claimed_with_a_pr_url_to_prove_it(monkeypatch: Any) -> None:
    app = _app()
    monkeypatch.setenv("HF_TOKEN", "fake-token")

    class NoUrl:
        def __init__(self, *a: Any, **k: Any) -> None: ...
        def upload_file(self, **kwargs: Any) -> Any:
            return SimpleNamespace()  # an API response carrying no pr_url

    monkeypatch.setattr("huggingface_hub.HfApi", NoUrl)
    out = app.submit_result("someorg/their-vla", str(APP))
    assert "Submitted —" not in out, "claimed success with no PR URL to point the submitter at"
    assert app.GUARANTEED_ROUTE in out, out

    class WithUrl:
        def __init__(self, *a: Any, **k: Any) -> None: ...
        def upload_file(self, **kwargs: Any) -> Any:
            return SimpleNamespace(pr_url="https://huggingface.co/datasets/x/y/discussions/1")

    monkeypatch.setattr("huggingface_hub.HfApi", WithUrl)
    ok = app.submit_result("someorg/their-vla", str(APP))
    assert "Submitted —" in ok, ok
    assert "discussions/1" in ok, "success message must carry the evidence"


def test_the_no_token_path_still_names_a_route_that_works() -> None:
    """Locally there is no HF_TOKEN. That message must not be a dead end either."""
    app = _app()
    out = app.submit_result("someorg/their-vla", str(APP))
    assert "Submitted" not in out or "queue disabled" in out.lower(), out
