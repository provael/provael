# Recipes — named run presets

A **recipe** is a named preset of `provael attack` options — the copy-paste shortcut that turns
"the benign control plus nine attacks across four families, ten episodes, seed 0" into one flag.

```bash
provael list-recipes                     # see the built-ins
provael attack --recipe quick            # run a built-in by name
provael attack --recipe ./examples/recipes/full-sweep.yml   # or load a YAML file
provael attack --recipe ci-gate --seed 7 # explicit flags override the recipe
```

| Recipe | Attacks | Episodes | Use it for |
| --- | --- | --- | --- |
| `quick` | instruction | 5 | fastest CPU smoke test |
| `instruction-only` | instruction | 10 | the EAI01 jailbreak family on its own |
| `core-sweep` | none + instruction, visual, injection, action | 10 | the four core families, all applicable on the CPU stub |
| `full-sweep` | none + **all 14** adversarial families | 10 | every family in the registry; inapplicable ones are skipped (N/A), never scored 0% |
| `ci-gate` | none + instruction, visual, injection, action | 10 (seed 0) | the preset a CI gate runs (matches `action.yml`) |

Every recipe includes **`none`**, the benign control. It is not optional: the release gate
requires it, and an ASR without a false-positive baseline cannot be interpreted. `full-sweep`
is derived from the attack registry at import, so a newly-registered family joins it
automatically — it used to be a hardcoded list of four beside a registry of fourteen.

The built-ins ship **inside the package**, so `provael --recipe quick` works straight from
`pip install provael`. The `.yml` files here mirror those built-ins as editable templates: copy
one, change a field, and pass it with `--recipe ./your-recipe.yml`. A recipe file is just a
mapping of [`RunConfig`](../../src/provael/config.py) fields.
