# Reproduce this run

Everything another engineer needs to attempt the run; nothing here is a promise that the numbers come back identical — the policy samples its actions, so a re-execution matches in distribution, not byte for byte.

## Pinned inputs

- provael: `0.41.2` (`pip install 'provael[lerobot]==0.41.2'`), with `lerobot[libero]==0.5.1` as the lane pins it
- Checkpoint: `HuggingFaceVLA/smolvla_libero` (the shards' `deployed_policy` records no resolved revision — pin one by hand before you run, and record it)
- Suite: `libero`, tasks `libero_object/0` … `libero_object/9` (10)
- Arms: `decoy_object`, `goal_substitution`, `mcp_tool_desc`, `none`, `paraphrase`, `patch`, `roleplay`, `scene_text`
- Seeds: 5 (base seed 0); horizon 280; 5 episode(s) per (task, arm) per shard
- Recorded environment: OS Linux 6.6.87.2-microsoft-standard-WSL2; Python 3.12.14; hardware `x86_64` (the manifests name no accelerator model; the README of the run says which box ran it)
- Source commit of the committed run: `5690df5`; the shards themselves record no commit

## Command shape

One task per container, the lane's design (a ten-task LIBERO screen is ~15 GPU-hours):

```bash
# the driver: examples/gpu-ci/modal_libero_suite.py (Modal); or per task, locally on a CUDA box:
export PROVAEL_REPOSITORY=provael/provael PROVAEL_COMMIT=<sha you are running>
provael attack --policy smolvla --suite libero --model HuggingFaceVLA/smolvla_libero \
    --tasks libero_object/<i> --attacks decoy_object,goal_substitution,mcp_tool_desc,none,paraphrase,patch,roleplay,scene_text \
    --seeds 5 --horizon 280 --seed 0 \
    --protocol examples/assessment/protocol.example.yml --out runs/libero_object_<i>
```

## Expected qualitative behaviour

- `roleplay` well above the benign floor on the Object suite (42/50 here, task-clustered interval in the README); `goal_substitution` and `paraphrase` above the floor but far below it; the visual and injection arms at or near the floor; `mcp_tool_desc` not applicable.
- Clean task success on the benign arm above 0.9.
- Under the example protocol the decision is FAIL on the roleplay slice.

## Known limits of a reproduction

- Cross-seed spread on LIBERO is ~14 percentage points; compare intervals, not points.
- A different lerobot or MuJoCo version is a different simulator; record both.
- The default predicate is the documented box; a calibrated run is a different measurement.
