# Paper L5 Model Comparison

Side-by-side L5 rewrites from DeepSeek-V4-Flash and Qwen3-235B-A22B for 30
traceable academic-paper samples. Both models receive the same source segment,
prompt, temperature, top-p, and generation limit.

## Open the review

- GitHub-native review: [review.md](review.md)
- Primary: https://lyumanshanye.github.io/paper-l4l5-compare/index.html
- Alternate path: https://lyumanshanye.github.io/paper-l4l5-compare/l5.html

The review is a self-contained static page. It shows each original paper segment
and both L5 rewrite diffs. L4 is intentionally excluded from the current UI.
Use the GitHub-native review when `github.io` is unavailable on the current
network; it renders entirely on `github.com` without JavaScript.

## Contents

- `index.html`, `l5.html`, and `paper30.html`: L5-only comparison page
- `review.md` and `reviews/`: GitHub-native comparison pages
- `results/`: inference results, samples, and retrieval manifest
- `scripts/`: reproducible retrieval, sampling, inference, and page-generation scripts
