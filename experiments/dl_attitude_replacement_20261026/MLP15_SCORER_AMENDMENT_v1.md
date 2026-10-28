# MLP15 scorer amendment v1

The first v2 scorer attempt stopped before reading candidate raw files. Its frozen source pointed at the v1 pilot taskbook, while the v2 candidate release binds MLP15_CLOSED_LOOP_PILOT_TASKBOOK_v2.md. The file hash check correctly stopped scoring; no result file was written and no Plant call occurred.

The v2r scorer changes that one taskbook path and binds its own source hash through MLP15_SCORE_RELEASE_v1.json. It reads the original v2 candidate release, the same six raw outputs, and the same B/C5/C5_10 references. Candidate runs, model, inputs, metrics, tolerances, and acceptance gates are unchanged. A tilt-limited scene remains ineligible for pilot advancement under the frozen v2 taskbook.