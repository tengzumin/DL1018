# Root approval: fixed SO(3) task-attitude blend shadow

Date: 2026-10-27 (Asia/Shanghai)

I reviewed and approve the diagnostic scope in `ROOT_TASKBOOK_TASK_ATTITUDE_BLEND_SHADOW_v1.md` (SHA-256 `025ca251657978f857cb61128eeaa5a2d8ce656937541256102bec928045e24f`). The frozen coefficient is beta=0.25, on the 56 already-locked Candidate/C5 W09-W14 raws only. This approval authorizes isolated script preparation and, after script review, one offline replay under the taskbook. It does not authorize any Plant/closed-loop run, training, source/model/config edit, B raw access, TEST read, or expansion to other scenes.

I independently recomputed hashes of the candidate runner, shared command filter, force-to-attitude adapter, locked config, and prior by-scene path table. They match the values recorded in the taskbook. The gate (Candidate task-to-counterfactual-filtered RMSE <=58.949 mrad, identity replay passing, and no tilt-cap violation) is coherent with the stated goal of closing at least half of the frozen +3.176 mrad gap to B.

The script must remain under this taskbook directory. It must inspect MAT/HDF5 structure without copying or materializing prohibited variables; read only the taskbook's whitelisted datasets; verify locked raw identities before reading; and reproduce the original filter log from the initial logged filter state before any blend result is reported. **Execution remains withheld until root reviews and approves the final script hash.** Any schema mismatch, inaccessible selective reads, identity mismatch, or replay mismatch means abort without interpreting a counterfactual.
