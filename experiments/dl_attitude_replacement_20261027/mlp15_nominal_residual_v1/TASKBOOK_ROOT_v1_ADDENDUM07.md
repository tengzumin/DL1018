# Root taskbook addendum 07: retry the interrupted offline score in one Python environment

This addendum follows ADDENDA05–06 and the REPAIR02 executor review. The REPAIR02 run passed the 48-scene metadata audit and frozen scorer preflight, then wrote `STARTED_ONE_SHOT` before the first progress record. It exited with OpenMP Error #15 because the base Anaconda Python loaded NumPy/HDF5 from Anaconda and PyTorch from the user site, which exposes two different `libiomp5md.dll` binaries. The progress file is empty, no scene completed, and no score/result/summary arrays exist. Whether the first scene's numerical arrays were read is unknown; preserve this as a partial failed attempt and never report its partial read as a result.

## Authorized recovery

Use a fresh `C5_VAL48_OFFLINE_DIAGNOSTIC_REPAIR03` directory and a single coherent Python environment. The existing `TCN0906` conda environment has been checked to import NumPy 2.2.6, h5py 3.16.0, and PyTorch 2.5.1 together; a NumPy matrix multiply, a CPU tensor operation, and loading the frozen 60,000-step checkpoint all passed. Do not set `KMP_DUPLICATE_LIB_OK` or change controller/scoring code to suppress the runtime error.

Prepare a new executor/lock bound to ADDENDUM07, the approved REPAIR02 review, the frozen inputs, and the unchanged parity bundle. Root reviews the final script/lock before release. Then permit exactly one complete 48-scene C5_VAL48 diagnostic under `TCN0906`, with the same checkpoint, labels, score rules, and zero-residual baseline. Any incomplete run remains failed and no further retry is authorized by this addendum.

No training, tuning, TEST access, B/C5 rerun, Plant call, or closed-loop run is authorized. This is reused validation only and cannot establish closed-loop attitude improvement.
