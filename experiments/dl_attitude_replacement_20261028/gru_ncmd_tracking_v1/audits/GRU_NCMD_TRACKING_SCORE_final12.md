# NCMD-GRU tracking paired score

Status: **COMPLETE_12_SCREEN**. Completed scenes: 12/12.

Fixed 12-scene DEV/VAL development screen; the parent GRU used DEV24+VAL48 development evidence, VAL is not independent validation, and this study adds no training.
Actual wind groups are read from `scene/environment_wind_I` in each candidate raw MAT; zero wind means every stored component is exactly zero.

| Group | n / expected | Complete | Method | Q (m) | task SO(3) (rad) | inner SO(3) (rad) |
|---|---:|:---:|---|---:|---:|---:|
| ALL12 | 12 / 12 | yes | Candidate | 0.00977429408 | 0.046881718 | 0.0109951088 |
| ALL12 | 12 / 12 | yes | Parent_Cosine_GRU | 0.00969077313 | 0.046525441 | 0.0114750373 |
| ALL12 | 12 / 12 | yes | B | 0.014306172 | 0.0501582114 | 0.0127607496 |
| ALL12 | 12 / 12 | yes | C5 | 0.0100796405 | 0.0465109297 | 0.0128647829 |
| HF_W09_W14 | 6 / 6 | yes | Candidate | 0.0102053633 | 0.0613504684 | 0.013704656 |
| HF_W09_W14 | 6 / 6 | yes | Parent_Cosine_GRU | 0.0101411273 | 0.0611989934 | 0.014410202 |
| HF_W09_W14 | 6 / 6 | yes | B | 0.0112657697 | 0.0576186242 | 0.0161929971 |
| HF_W09_W14 | 6 / 6 | yes | C5 | 0.0105837878 | 0.0612040974 | 0.0164247501 |
| W15 | 3 / 3 | yes | Candidate | 0.00614891193 | 0.00417248359 | 0.0154661468 |
| W15 | 3 / 3 | yes | Parent_Cosine_GRU | 0.00588118933 | 0.0030547295 | 0.0165349928 |
| W15 | 3 / 3 | yes | B | 0.00805307444 | 0.00597924525 | 0.0184923481 |
| W15 | 3 / 3 | yes | C5 | 0.00655036148 | 0.00298179183 | 0.0184914344 |
| W00_W08 | 3 / 3 | yes | Candidate | 0.0125375377 | 0.0606534515 | 0.00110497656 |
| W00_W08 | 3 / 3 | yes | Parent_Cosine_GRU | 0.0125996487 | 0.060649048 | 0.000544752488 |
| W00_W08 | 3 / 3 | yes | B | 0.0266400742 | 0.0794163521 | 0.000164656141 |
| W00_W08 | 3 / 3 | yes | C5 | 0.012600625 | 0.0606537324 | 0.000118197201 |
| ZERO_RAW_WIND | 3 / 3 | yes | Candidate | 0.00614891193 | 0.00417248359 | 0.0154661468 |
| ZERO_RAW_WIND | 3 / 3 | yes | Parent_Cosine_GRU | 0.00588118933 | 0.0030547295 | 0.0165349928 |
| ZERO_RAW_WIND | 3 / 3 | yes | B | 0.00805307444 | 0.00597924525 | 0.0184923481 |
| ZERO_RAW_WIND | 3 / 3 | yes | C5 | 0.00655036148 | 0.00298179183 | 0.0184914344 |
| NONZERO_RAW_WIND | 9 / 9 | yes | Candidate | 0.0109827548 | 0.0611181294 | 0.00950476284 |
| NONZERO_RAW_WIND | 9 / 9 | yes | Parent_Cosine_GRU | 0.0109606344 | 0.0610156782 | 0.0097883855 |
| NONZERO_RAW_WIND | 9 / 9 | yes | B | 0.0163905379 | 0.0648845335 | 0.0108502168 |
| NONZERO_RAW_WIND | 9 / 9 | yes | C5 | 0.0112560669 | 0.0610206424 | 0.0109892325 |

Actual raw-wind groups:
- ZERO_RAW_WIND: 3/3 scored scenes
- NONZERO_RAW_WIND: 9/9 scored scenes

Pending or failed scenes:
- none
