# Policy & political-scenario impact

Open `/policy-impact/Sugar` or `/policy-impact/Onion`. Each scenario separates its trigger, direction, magnitude band, horizon, confidence, causal mechanism, watch indicators and sources. `/api/policy-impact/{commodity}` returns the same audit-ready JSON. `/policy-impact/{commodity}/report.pdf` creates a shareable PDF without an extra system dependency.

The included ranges are scenario-conditioned heuristics, not trained point forecasts. They must be walk-forward tested before production use. If a commodity has no specific policy model, the platform returns a low-confidence generic ENSO/rainfall scenario rather than pretending crop-specific precision.

Compatibility wrappers: `npm run build` validates Python syntax and the PDF generator; `npm start` uses the existing `uv run vervana serve` flow.
