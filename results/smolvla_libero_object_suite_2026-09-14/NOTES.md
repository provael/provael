The published SmolVLA x LIBERO-Object measurement, re-run on a current release. The committed
result this repeats is `results/smolvla_libero_object_suite` (provael 0.32.0, 9 August 2026:
roleplay 44/50, `none` 2/50). This run used the same checkpoint, the same ten tasks, the same eight
arms, five seeds and horizon 280, on provael 0.41.2 from PyPI, on a workstation RTX 2000 Ada
rather than a cloud L4. Roleplay is 42/50 here against 44/50 there; the intervals overlap almost
entirely, and no other arm moved outside its interval. The number reproduces.

Read it together with `results/smolvla_libero_object_control_2026-09-14`, which ran the
harmless-variation controls against the same tasks the same day. Those controls change what the
roleplay rate means, and the NOTES there say how. The two directories are separate because they
were separate runs; nothing here was pooled with them.

The execution manifests record `commit: null`, `repository: null`, `dep_lock_digest: null` and
`precision: null`: the installed 0.41.2 wheel did not read the variables the driver set, and had
no code to fill the other three. That is the gap the scheduled lane's provenance gate now refuses
(see `provael.campaign`); it is recorded here rather than back-filled, because provenance that is
reconstructed after the run is not provenance. The `tool_version` and the checkpoint are in every
report; the release's tag commit is public.
