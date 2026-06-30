# Recipes — named run presets

A **recipe** is a named preset of `provael attack` options — the copy-paste shortcut that turns
"nine attacks across four families, ten episodes, seed 0" into one flag.

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
| `full-sweep` | instruction, visual, injection, action | 10 | the complete four-family scan |
| `ci-gate` | instruction, visual, injection, action | 10 (seed 0) | the preset a CI gate runs |

The built-ins ship **inside the package**, so `provael --recipe quick` works straight from
`pip install provael`. The `.yml` files here mirror those built-ins as editable templates: copy
one, change a field, and pass it with `--recipe ./your-recipe.yml`. A recipe file is just a
mapping of [`RunConfig`](../../src/provael/config.py) fields.
