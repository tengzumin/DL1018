# Root approval v2: fixed SO(3) task-attitude blend shadow

Date: 2026-10-27 (Asia/Shanghai)

I reviewed the source-hash correction recorded in `AMENDMENT_source_hash_v1.md` and the corrected taskbook SHA-256 `f7ca704374eb4d5a0ed24ab1221f46e679ac713df12fa3baaf8e4359bfe19c57`. The actual PowerShell 7 SHA-256 of `command_filter_step.m` is `15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b`; it now matches the taskbook and script lock.

The first attempt is preserved as `ABORT_RECORD_attempt01.json` and stopped before any raw was opened. The correction changes only the source identity string; scope, beta, inputs, metrics, and gate remain unchanged. I approve one offline shadow execution under the corrected taskbook, provided the new script hash is approved separately. No Plant/closed-loop run, training, production edit, B raw access, or TEST read is authorized.
