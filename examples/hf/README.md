# Hugging Face — push ASR onto the model page

[`emit_eval_results.py`](emit_eval_results.py) writes a Provael ASR as a Hugging Face eval result
(`.eval_results` YAML). Adding it to a policy's model card makes Provael self-distributing and
feeds the leaderboard.

```bash
pip install huggingface_hub provael
python examples/hf/emit_eval_results.py     # writes eval_results.yaml
```

**Gated:** uploading the result to *another org's* model repo is an external write — open a PR
(community-provided eval), never push directly.
