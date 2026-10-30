# Demonstration guide (about 2 minutes 35 seconds)

The supplied example is synthetic. Use the actual motor STEP for the final
manufacturer-part demonstration. Subscription mode makes real cloud model calls;
offline commands and `scripts/demo.py` do not. Never present the latter as live AI.

| Time | Action |
| --- | --- |
| 0:00–0:20 | Load synthetic_motor.step or the supplied actual motor. Orbit the source and show the measured interface. |
| 0:20–0:45 | Describe six parts for continuous running. Show the real planner asking for stationary meaning, motion/loads and bench attachment. |
| 0:45–1:10 | Answer with known facts or explicit unknowns. Confirm hole selection and clearance, review assumptions and compare the two supported proposals. |
| 1:10–1:45 | Generate the plate. Show aligned sources, 24 holes for this sample, individual checks and unevaluated operating performance. |
| 1:45–2:20 | Request open supports for rear tool access. Generate the revision, compare volume/body composition and preserve measured holes. |
| 2:20–2:35 | Restore a previous revision if desired; export the ZIP. Explain real SMLib BRep and reproducible records. |

Trim actual waiting transparently if editing a recording. The live subscription
test record is `live-subscription-record.json`; its three actions came from actual
model calls. `live-subscription-export.zip` is the resulting native CAD bundle.
`assembly.html` is a standalone interactive viewer from the deterministic demo.

No continuous screen recording has been captured in this implementation run.
