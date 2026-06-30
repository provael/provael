# Bring-your-own-VLA cookbook

Provael red-teams **any** policy that implements the tiny
[`PolicyAdapter`](../../src/provael/policies/base.py) contract:

```python
class PolicyAdapter(ABC):
    def set_features(self, features): ...   # optional: receive env metadata (cameras, action dim)
    def reset(self): ...                    # optional: clear per-episode state (action-chunk queue)
    def load(self): ...                     # load weights; raise a clear error if a dep is missing
    def act(self, observation, instruction) -> np.ndarray: ...   # the only required mapping
```

That's the whole integration surface. A runnable, CPU-only example is
[`../python-api/custom_policy_adapter.py`](../python-api/custom_policy_adapter.py):

```bash
python examples/python-api/custom_policy_adapter.py
```

Below are the three backends you'll actually wire to.

## 1. A LeRobot policy

Already done for you — `smolvla`, `pi0`, `pi05`, `pi0fast`, `groot` are registered and load
through LeRobot's generic path. To register a *new* LeRobot-native checkpoint, add one line to
[`registry.py`](../../src/provael/policies/registry.py):

```python
POLICIES["my-lerobot-vla"] = _lerobot_native("org/my-checkpoint", "my-lerobot-vla")
```

## 2. A Hugging Face `transformers` AutoModel

Pattern is [`openvla_adapter.py`](../../src/provael/policies/openvla_adapter.py): import torch /
transformers **inside `load()`** (never at module top, so the CPU core stays importable), build
the processor + model, and in `act()` turn `(image, instruction)` into your model's input and
return its action as a 1-D numpy array. Clamp with
`provael.policies.lerobot_adapter.clamp_action`.

```python
class MyHFVLA(PolicyAdapter):
    name = "my-hf-vla"
    def load(self):
        import torch
        from transformers import AutoModelForVision2Seq, AutoProcessor
        self.proc = AutoProcessor.from_pretrained(self.model_id, trust_remote_code=True)
        self.model = AutoModelForVision2Seq.from_pretrained(self.model_id, trust_remote_code=True).to("cuda")
    def act(self, obs, instruction):
        inputs = self.proc(self.prompt(instruction), to_pil(obs["image"])).to("cuda")
        return clamp_action(self.model.predict_action(**inputs, unnorm_key=self.key), 7)
```

## 3. A remote policy server (HTTP / websocket / ZMQ)

For a 7B+ model served off-host (e.g. openpi's websocket server, GR00T's ZMQ server) you can
red-team from a **CPU** runner — `act()` just RPCs the action:

```python
class MyRemoteVLA(PolicyAdapter):
    name = "my-remote-vla"
    def load(self):
        import websocket  # or your client
        self.conn = connect(self.url)
    def act(self, obs, instruction):
        action = self.conn.infer({"image": obs["image"], "task": instruction})["action"]
        return clamp_action(np.asarray(action), 7)
```

## Register and run

```python
from provael.policies.registry import POLICIES
from provael.config import RunConfig
from provael.runner import run

POLICIES["my-vla"] = lambda **_: MyVLA()
report = run(RunConfig(policy="my-vla", suite="stub", attacks=["instruction"], episodes=10))
print(report.headline())
```

Swap `suite="stub"` for `"libero"` (or any registered suite) to red-team in a real simulator.
Every attack family works unchanged — that's the point of the adapter boundary.
