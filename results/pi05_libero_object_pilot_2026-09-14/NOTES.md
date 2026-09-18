The first π0.5 rollouts through provael's native `pi05` adapter: `lerobot/pi05_libero_finetuned_v044`,
benign arm only, two tasks, five seeds. Its two questions were competence and cost. Clean task
success 10/10; 1,315 policy steps in 511 s of wall clock including model load, 0.39 s per step on
an RTX 2000 Ada. No attack ran; nothing here is a rate. The π0.5 LIBERO-Object run with the attack
arm follows from this timing.
