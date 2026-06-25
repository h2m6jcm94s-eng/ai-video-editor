# Prompt-Edit Improvement Changelog

This document tracks iterative prompt edits on the car-meet fixture project.
The goal is to improve the cutlist with each edit, keep changes that raise the
heuristic score, and record why each change was kept or reverted.

## Run metadata

| Field | Value |
|-------|-------|
| Project ID | `TBD` |
| Baseline score | `TBD` |
| Best score | `TBD` |
| Total iterations | `TBD` |
| Timestamp | `TBD` |

## Scoring weights

| Dimension | Weight | Rationale |
|-----------|--------|-----------|
| Pacing | 0.25 | Moderate shot-duration variety keeps energy without jarring cuts. |
| Sync | 0.20 | Cuts aligned to the beat grid feel musical and intentional. |
| Diversity | 0.20 | Reusing clips and shot types too often makes the edit repetitive. |
| Energy arc | 0.20 | A rising/falling energy curve matches song structure and viewer attention. |
| Transition variety | 0.15 | Mixing transitions adds polish; all hard cuts feel raw. |

## Iterations

| # | Prompt | Score before | Score after | Decision | What changed and why |
|---|--------|--------------|-------------|----------|----------------------|
| 0 | *Baseline* | — | — | — | Starting cutlist from generation. |

## Summary

*After the sweep completes, summarize the highest-scoring cutlist and the most
effective prompts here.*
