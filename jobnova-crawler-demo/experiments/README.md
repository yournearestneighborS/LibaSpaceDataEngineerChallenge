# Experiment checklist

Do not publish benchmark numbers until all ten manifest entries have manually verified ground truth.

1. Run `prepare-ground-truth` from `TAKE_HOME_SUBMISSION.md`.
2. Review the rendered live page and candidate text side by side.
3. Save approved text in `experiments/ground_truth/{id}.txt`.
4. Change only that entry's `verified` flag to `true`.
5. Run `benchmark` for all three modes.
6. Inspect `page_results.csv` for zero-length or suspicious outputs.
7. Copy the aggregate `comparison.csv` table into the final submission.

The manifest's `as_of` date should be updated whenever URLs or ground truth are refreshed.

