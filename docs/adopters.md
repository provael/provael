# Adopters

**This page is the sign-up sheet: a self-reported list teams add themselves to by pull request.**
It is not a measurement of anything, and it is one of two pages named "adopters" — see the box
below before you cite either.

It exists so a new user can see the tool in real use, and so adopters can find each other. An entry
means a team said they use Provael to red-team a VLA policy — in CI, in research, or as part of a
compliance-evidence workflow.

!!! warning "Two pages are called 'Adopters' and they mean different things"

    | | This page (`docs/adopters.md`) | [provael.com/adopters](https://provael.com/adopters) |
    | --- | --- | --- |
    | What it is | a **sign-up sheet** | a **measurement** |
    | Where the data comes from | teams adding themselves by PR | PyPI downloads, GitHub stars, forks |
    | Current state | **empty** — nobody has signed up | populated, and deliberately unflattering |
    | What it can tell you | who is willing to say so publicly | how much the package is actually pulled |

    They are not versions of each other and neither supersedes the other. **An empty list here is
    not evidence of no users** — it is evidence that nobody has opened a PR, which is a different
    and much weaker claim. The download figures on the site are the number to look at if you want
    to know whether anyone runs this; the ratio between them is the point of that page.

> Status: PLANNED — no results claimed. This list is community-maintained and self-reported. An
> entry is a statement by the adopter, not an endorsement by Provael, and carries no measured
> Attack Success Rate or transfer claim.

## Add yourself

Open a pull request that adds one row to the table below. Keep it plain text — **no logos, no
marketing copy**:

- **Organization** — your team, company, lab, or handle, exactly as you want it cited. A link on
  the name is welcome but optional.
- **Use case** — one honest line on how you use Provael (e.g. "CI gate on our SmolVLA fork",
  "coursework on embodied-AI security", "pre-deployment evidence for an internal review").
- **Since** — the month you started, as `YYYY-MM`.

Add the row in alphabetical order by organization, and sign the commit off (`git commit -s`) like
any other contribution.

## Adopters

| Organization | Use case | Since |
| --- | --- | --- |
| _No public adopters have signed up yet._ | | |

**What this empty table does and does not say.** It says zero teams have opened a PR to add
themselves. It does **not** say zero teams use Provael — the measured distribution figures on
[provael.com/adopters](https://provael.com/adopters) are the number for that question, and they are
not zero. Reading an empty sign-up sheet as an empty user base is the mistake this note exists to
prevent, in both directions.
