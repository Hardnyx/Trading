# Repository workflow

- Commit authorized changes directly to `main`. Do not create pull requests or auxiliary review branches.
- Fetch `origin/main` before publishing and preserve concurrent changes.
- Preserve existing history unless the user explicitly requests a history rewrite.
- For changes affecting forecasts or composition, keep a frozen-input audit that separates data changes, model corrections, Monte Carlo noise and search uncertainty. Do not tune seeds or preserve previous weights merely to make recommendations look stable.
- Test mathematical invariants and decision safeguards. Passing software tests or finding similar weights is not evidence of predictive or economic validity. State unresolved allocation ranges and limits of prospective evidence.
- Increment `PRICE_KERNEL_VERSION` for material changes to the return law, anchoring rules, volatility procedure or causal forecast definition. Preserve old cohorts and do not pool them as evidence for a changed kernel.
