# E2 — SLA window {24, 48, 72, 120}h

Escalation response_rate is held fixed across all four cells (grid.py's own
E2_RESPONSE_RATE) so the x-axis means only the SLA window, not a second swept
assumption.

| sla_window_hours | closure_rate | escalations_raised | escalations_per_100_referrals | escalations_false_positive | n_seeds |
|---|---|---|---|---|---|
| 24 | 0.778 | 26 | 42.693 | 0 | 3 |
| 48 | 0.804 | 26 | 42.693 | 0 | 3 |
| 72 | 0.785 | 26 | 42.693 | 0 | 3 |
| 120 | 0.786 | 26 | 42.693 | 0 | 3 |
