**Uses:** 2265 (152 break, 2113 work) in 171 upgrades of the 2026-11f holdout.


### Abstentions count as not flagged

How a check on a pull request behaves: an answer that isn't `breaks` doesn't fail it.

| Answered by | Breaks found (recall) | Working uses flagged | Precision | Abstained |
|---|---|---|---|---|
| DepTime `check_symbols`, first run | 96.7% (147/152; 92.5-98.6) | 0.1% (2/2113; 0.0-0.3) | 98.7% (147/149; 95.2-99.6) | - |
| DepTime `diff_versions`, first run | 96.7% (147/152; 92.5-98.6) | 0.1% (2/2113; 0.0-0.3) | 98.7% (147/149; 95.2-99.6) | - |
| Rule: everything works | 0.0% (0/152; 0.0-2.5) | 0.0% (0/2113; 0.0-0.2) | - | - |
| Rule: breaks when the first number differs | 76.3% (116/152; 69.0-82.4) | 35.8% (757/2113; 33.8-37.9) | 13.3% (116/873; 11.2-15.7) | - |
| Rule: breaks when the series differs (0.x: the second number) | 90.1% (137/152; 84.4-93.9) | 53.2% (1124/2113; 51.1-55.3) | 10.9% (137/1261; 9.3-12.7) | - |
| Rule: everything breaks going down | 41.4% (63/152; 33.9-49.4) | 37.5% (793/2113; 35.5-39.6) | 7.4% (63/856; 5.8-9.3) | - |

### Abstentions apart

As the holdout's own results count them (`../../holdout/score.py`).

| Answered by | Breaks found (recall) | Working uses flagged | Precision | Abstained |
|---|---|---|---|---|
| DepTime `check_symbols`, first run | 100.0% (147/147; 97.5-100.0) | 0.1% (2/2047; 0.0-0.4) | 98.7% (147/149; 95.2-99.6) | 5 breaks, 66 works |
| DepTime `diff_versions`, first run | 96.7% (147/152; 92.5-98.6) | 0.1% (2/2113; 0.0-0.3) | 98.7% (147/149; 95.2-99.6) | 0 breaks, 0 works |
| Rule: everything works | 0.0% (0/152; 0.0-2.5) | 0.0% (0/2113; 0.0-0.2) | - | 0 breaks, 0 works |
| Rule: breaks when the first number differs | 76.3% (116/152; 69.0-82.4) | 35.8% (757/2113; 33.8-37.9) | 13.3% (116/873; 11.2-15.7) | 0 breaks, 0 works |
| Rule: breaks when the series differs (0.x: the second number) | 90.1% (137/152; 84.4-93.9) | 53.2% (1124/2113; 51.1-55.3) | 10.9% (137/1261; 9.3-12.7) | 0 breaks, 0 works |
| Rule: everything breaks going down | 41.4% (63/152; 33.9-49.4) | 37.5% (793/2113; 35.5-39.6) | 7.4% (63/856; 5.8-9.3) | 0 breaks, 0 works |

Rates with 95% Wilson intervals. Uses within one project aren't independent, so the intervals are narrower than they should be; the per-upgrade table is the check on that.

### Per upgrade

| Answered by | Upgrades where every use works, with a false alarm | Upgrades with a break, at least one found |
|---|---|---|
| DepTime `check_symbols`, first run | 0.0% (0/144; 0.0-2.6) | 96.3% (26/27; 81.7-99.3) |
| DepTime `diff_versions`, first run | 0.0% (0/144; 0.0-2.6) | 96.3% (26/27; 81.7-99.3) |
| Rule: everything works | 0.0% (0/144; 0.0-2.6) | 0.0% (0/27; 0.0-12.5) |
| Rule: breaks when the first number differs | 34.0% (49/144; 26.8-42.1) | 59.3% (16/27; 40.7-75.5) |
| Rule: breaks when the series differs (0.x: the second number) | 51.4% (74/144; 43.3-59.4) | 81.5% (22/27; 63.3-91.8) |
| Rule: everything breaks going down | 34.0% (49/144; 26.8-42.1) | 55.6% (15/27; 37.3-72.4) |

### Splits (fixed in advance; abstentions count as not flagged)

Each cell is the breaks found, then the working uses flagged.

**Direction** (`down`: the code was written for a newer release than the one it gets):

| direction | uses (breaks/works) | DepTime `check_symbols`, first run | DepTime `diff_versions`, first run | Rule: everything works | Rule: breaks when the first number differs | Rule: breaks when the series differs (0.x: the second number) | Rule: everything breaks going down |
|---|---|---|---|---|---|---|---|
| down | 856 (63/793) | 98.4% (62/63; 91.5-99.7); flagged 0.0% (0/793; 0.0-0.5) | 98.4% (62/63; 91.5-99.7); flagged 0.0% (0/793; 0.0-0.5) | 0.0% (0/63; 0.0-5.7); flagged 0.0% (0/793; 0.0-0.5) | 55.6% (35/63; 43.3-67.2); flagged 21.1% (167/793; 18.4-24.0) | 82.5% (52/63; 71.4-90.0); flagged 44.5% (353/793; 41.1-48.0) | 100.0% (63/63; 94.3-100.0); flagged 100.0% (793/793; 99.5-100.0) |
| up | 1409 (89/1320) | 95.5% (85/89; 89.0-98.2); flagged 0.2% (2/1320; 0.0-0.6) | 95.5% (85/89; 89.0-98.2); flagged 0.2% (2/1320; 0.0-0.6) | 0.0% (0/89; 0.0-4.1); flagged 0.0% (0/1320; 0.0-0.3) | 91.0% (81/89; 83.3-95.4); flagged 44.7% (590/1320; 42.0-47.4) | 95.5% (85/89; 89.0-98.2); flagged 58.4% (771/1320; 55.7-61.0) | 0.0% (0/89; 0.0-4.1); flagged 0.0% (0/1320; 0.0-0.3) |

**The newer of the two releases**, by its upload to PyPI (`released.json`), against the training cutoff:

| newer_release | uses (breaks/works) | DepTime `check_symbols`, first run | DepTime `diff_versions`, first run | Rule: everything works | Rule: breaks when the first number differs | Rule: breaks when the series differs (0.x: the second number) | Rule: everything breaks going down |
|---|---|---|---|---|---|---|---|
| by 2026-06-30 | 782 (55/727) | 98.2% (54/55; 90.4-99.7); flagged 0.0% (0/727; 0.0-0.5) | 98.2% (54/55; 90.4-99.7); flagged 0.0% (0/727; 0.0-0.5) | 0.0% (0/55; 0.0-6.5); flagged 0.0% (0/727; 0.0-0.5) | 43.6% (24/55; 31.4-56.7); flagged 19.1% (139/727; 16.4-22.1) | 81.8% (45/55; 69.7-89.8); flagged 46.6% (339/727; 43.0-50.3) | 92.7% (51/55; 82.7-97.1); flagged 88.0% (640/727; 85.5-90.2) |
| from 2026-07-01 (after the cutoff) | 1483 (97/1386) | 95.9% (93/97; 89.9-98.4); flagged 0.1% (2/1386; 0.0-0.5) | 95.9% (93/97; 89.9-98.4); flagged 0.1% (2/1386; 0.0-0.5) | 0.0% (0/97; 0.0-3.8); flagged 0.0% (0/1386; 0.0-0.3) | 94.8% (92/97; 88.5-97.8); flagged 44.6% (618/1386; 42.0-47.2) | 94.8% (92/97; 88.5-97.8); flagged 56.6% (785/1386; 54.0-59.2) | 12.4% (12/97; 7.2-20.4); flagged 11.0% (153/1386; 9.5-12.8) |

**Whether the release series differs** (the first number, or the first two below 1.0), which the question shows:

| series | uses (breaks/works) | DepTime `check_symbols`, first run | DepTime `diff_versions`, first run | Rule: everything works | Rule: breaks when the first number differs | Rule: breaks when the series differs (0.x: the second number) | Rule: everything breaks going down |
|---|---|---|---|---|---|---|---|
| differs | 1261 (137/1124) | 96.4% (132/137; 91.7-98.4); flagged 0.0% (0/1124; 0.0-0.3) | 96.4% (132/137; 91.7-98.4); flagged 0.0% (0/1124; 0.0-0.3) | 0.0% (0/137; 0.0-2.7); flagged 0.0% (0/1124; 0.0-0.3) | 84.7% (116/137; 77.7-89.8); flagged 67.3% (757/1124; 64.6-70.0) | 100.0% (137/137; 97.3-100.0); flagged 100.0% (1124/1124; 99.7-100.0) | 38.0% (52/137; 30.3-46.3); flagged 31.4% (353/1124; 28.8-34.2) |
| same | 1004 (15/989) | 100.0% (15/15; 79.6-100.0); flagged 0.2% (2/989; 0.1-0.7) | 100.0% (15/15; 79.6-100.0); flagged 0.2% (2/989; 0.1-0.7) | 0.0% (0/15; 0.0-20.4); flagged 0.0% (0/989; 0.0-0.4) | 0.0% (0/15; 0.0-20.4); flagged 0.0% (0/989; 0.0-0.4) | 0.0% (0/15; 0.0-20.4); flagged 0.0% (0/989; 0.0-0.4) | 73.3% (11/15; 48.0-89.1); flagged 44.5% (440/989; 41.4-47.6) |

**Change type of each break** (breaks found):

| change | breaks | DepTime `check_symbols`, first run | DepTime `diff_versions`, first run | Rule: everything works | Rule: breaks when the first number differs | Rule: breaks when the series differs (0.x: the second number) | Rule: everything breaks going down |
|---|---|---|---|---|---|---|---|
| param_not_yet_added | 2 | 100.0% (2/2; 34.2-100.0) | 100.0% (2/2; 34.2-100.0) | 0.0% (0/2; 0.0-65.8) | 0.0% (0/2; 0.0-65.8) | 50.0% (1/2; 9.5-90.5) | 100.0% (2/2; 34.2-100.0) |
| param_removed | 3 | 100.0% (3/3; 43.8-100.0) | 100.0% (3/3; 43.8-100.0) | 0.0% (0/3; 0.0-56.2) | 66.7% (2/3; 20.8-93.9) | 66.7% (2/3; 20.8-93.9) | 0.0% (0/3; 0.0-56.2) |
| removed | 86 | 95.3% (82/86; 88.6-98.2) | 95.3% (82/86; 88.6-98.2) | 0.0% (0/86; 0.0-4.3) | 91.9% (79/86; 84.1-96.0) | 96.5% (83/86; 90.2-98.8) | 0.0% (0/86; 0.0-4.3) |
| symbol_not_yet_added | 61 | 98.4% (60/61; 91.3-99.7) | 98.4% (60/61; 91.3-99.7) | 0.0% (0/61; 0.0-5.9) | 57.4% (35/61; 44.9-69.0) | 83.6% (51/61; 72.4-90.8) | 100.0% (61/61; 94.1-100.0) |
