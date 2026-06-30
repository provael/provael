# Integrations — plug Provael into the tools security teams already use

Every "proven" red-team tool scores LLM/agent **text I/O**. Provael adds the **action-space**
dimension. These integrations let it ride those tools' existing runners and user bases — *"garak
scans what the model says; Provael scans what the robot does."*

| Tool | What it is | File | Status |
| --- | --- | --- | --- |
| [promptfoo](promptfoo/) | LLM red-team / eval runner (custom Python provider) | `provael_provider.py` | **runnable** (CPU stub) |
| [garak](garak/) | LLM vulnerability scanner (probe/detector plugin) | `provael_garak.py` | reference |
| [pyrit](pyrit/) | MS PyRIT attack orchestrator (PromptTarget) | `provael_target.py` | reference |

- **promptfoo** is fully runnable on CPU: `npx promptfoo@latest eval -c promptfoo/promptfooconfig.yaml`
  (the provider runs a Provael scan and returns the verdict + ASR for promptfoo asserts).
- **garak** and **pyrit** are *reference integrations*: the Provael measurement is the same code
  the package unit-tests, but the host-tool base-class glue is written against each tool's
  documented plugin shape and is not validated against an installed copy in this repo's CI. Each
  file is importable with or without its host tool present.

**Upstream contributions** (a garak probe pack, a PyRIT target, a promptfoo example) are natural
next steps — drafted here for review; **not** opened as upstream PRs from this repo without sign-off.
