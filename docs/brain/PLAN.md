# PLAN (status: TODO, DOING, DONE, STOP)
| ID | Task | Level | Needs | Findings | Status |
| T1 | Confirm F2 and F1b results (ask me for their reports; run only the checks they name) | MED | - | U1-U5, G1.. | DONE |
| T2 | F1c-fix | HIGH | T1 | H1-H7 | DONE |
| T2c | Reconcile caller status removal, auditor restriction, idempotent replay real state, may_release helper routing, FakePaymentRail param, exact webhook events | HIGH | T2 | Q1-Q5,Q8 | DONE |
| T3 | F1b fail closed, keys, schema, test DB, audits | HIGH | T2 | G1,G4-G8 | DONE |
| T4 | Env alignment after the password change | MED | T3 | N1 | DONE |
| T5 | STOP: YOU run reviewer R1 with a different model on git diff origin/main..HEAD, paste findings | HIGH | T4 | - | TODO |
| T6 | Fix R1 findings, then branches and Dependabot | MED | T5 | R2 | TODO |
| T7 | CI green; dev pushed; open PR dev to main. STOP: YOU merge on green | HIGH | T6 | C1 | DONE (dev pushed) |
| T8 | Real LLM in the demo path: Gemini 2.5 Flash Invoice Agent + Guardrails + Eval | MED | T7 | L1 | DONE |
| T9 | Hosted deploy configuration: render.yaml + Neon setup + verify script | MED | T7 | D1 | DONE |
| T10 | Real PayPal sandbox flow: Orders v2 flow, e1_sandbox_check.py, UI capture. STOP: YOU approve as the buyer | HIGH | T8,T9 | P1 | DONE |
| T11 | Sponsor polish (Gemini, Render, PayPal, AG Grid) | MED | T9 | S1 | DONE |
| T12 | Repo cleanup (hygiene, metrics, dependabot script) | MED | T10 | R3 | DONE |
| T13 | YOU: judge simulation J1 and a three-person UX test | - | T12 | X1 | TODO |
| T14 | YOU: truth audit V11 with a different model | HIGH | T13 | - | TODO |
| T15 | Devpost text and video script, shot list, claims matrix, judge FAQ authored | LOW | T14 | - | DONE |
| T16 | YOU: submit by Wed 11 Nov evening IST; tag after approval | - | T15 | - | TODO |
Cut order if behind: K1 numbers audit, then U4, then T12 polish. Never cut T2, T3, T10, a green CI or an honest README.
