# Supply chain — trust the model before you trust the ASR

A red-team result is only as good as the model you ran it on. These examples cover the
before-and-after of a scan.

| File | What it does |
| --- | --- |
| [`verify_model.py`](verify_model.py) | Prefer safetensors over (bypassable) pickle; verify a Sigstore model signature if present |
| [`mlbom_emit.py`](mlbom_emit.py) | Emit a CycloneDX **ML-BOM** with the ASR as a metric (ingests into OWASP Dependency-Track) |

```bash
python examples/supply-chain/verify_model.py /path/to/model_dir
python examples/supply-chain/mlbom_emit.py            # writes provael.mlbom.json
```

Ties Provael's evidence into the same supply-chain artifacts auditors already ask for (see
[docs/COMPLIANCE.md](../../docs/COMPLIANCE.md)).
