# Amendment: source hash correction

Date: 2026-10-27 (Asia/Shanghai)

During attempt 1, the script stopped during source/config preflight before opening any raw. The shared filter SHA in the draft taskbook and first script contained a one-character typo. The hash returned by PowerShell 7 for the locked source file is `15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b`.

The taskbook and script now bind this observed hash. No experiment scope, coefficient, input set, metric, threshold, or action changed. The aborted attempt is preserved in `ABORT_RECORD_attempt01.json`; the original MATLAB/raw result files remain untouched. A fresh script hash review is required before retrying.
