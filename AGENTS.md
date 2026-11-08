# Repository workflow

- Commit authorized changes directly to `main`. Do not create pull requests or auxiliary review branches.
- Use Conventional Commits in English. Describe concrete technical changes; avoid promotional wording, unsupported claims and generic AI phrasing.
- Fetch `origin/main` before publishing and preserve concurrent changes.
- Preserve existing history unless the user explicitly requests a history rewrite.
- For changes affecting forecasts or composition, keep a frozen-input audit that separates data changes, model corrections, Monte Carlo noise and search uncertainty. Do not tune seeds or preserve previous weights merely to make recommendations look stable.
- Test mathematical invariants and decision safeguards. Passing software tests or finding similar weights is not evidence of predictive or economic validity. State unresolved allocation ranges and limits of prospective evidence.
- Increment `PRICE_KERNEL_VERSION` for material changes to the return law, anchoring rules, volatility procedure or causal forecast definition. Preserve old cohorts and do not pool them as evidence for a changed kernel.
- Before validation work, read `docs/plan-validacion-predictiva.md`, select the first unblocked task on its critical path and state the milestone and acceptance criterion. New work must remove a documented blocker or follow an explicit user request.
- Update the outcome plan when delivering validation work: observed result, status, evidence cutoff, date, checks, published commit and remaining dependency. Keep technical deliverables separate from predictive and economic conclusions; data counts and passing software checks are not validation percentages.
