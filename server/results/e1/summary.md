# E1 — escalation {on, off} x dropout {10, 25, 40}%

Closure is reported two ways (ADR-017): the escalation-off arm is a measured
closure rate; the escalation-on arm is modelled as a function of an assumed
`escalation_response_rate`, swept over {0, 0.25, 0.5, 0.75}. The two are never
combined into one number.


- dropout=10%: escalation-off closure_rate=0.641

- dropout=25%: escalation-off closure_rate=0.573

- dropout=40%: escalation-off closure_rate=0.439
