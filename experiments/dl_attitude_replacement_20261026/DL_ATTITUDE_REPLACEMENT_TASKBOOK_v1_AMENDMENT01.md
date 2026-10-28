# Taskbook v1 amendment 01 — deterministic CUDA startup

Date: 2026-10-26. This amendment changes no dataset, label, network, optimizer, seed, step count, metric, or closed-loop gate in the frozen taskbook.

The first training launcher exited during its step-0 validation before the first optimizer update. `torch.use_deterministic_algorithms(True)` raised because CUDA had no `CUBLAS_WORKSPACE_CONFIG`; the run therefore completed **0/60,000 optimizer steps** and produced no trained candidate. Its output directory is preserved and marked failed.

The fixed configuration sets `CUBLAS_WORKSPACE_CONFIG=:4096:8` in the training script before importing PyTorch, records that value in the training config, and writes the same one-candidate/one-seed/60,000-step run to `training_v1_retry01/`. Source lock v1 remains immutable as the failed launcher record; source lock v2 pins the environment fix. The retry is the first training attempt that can produce the registered model. The setting is consistent with NVIDIA's documented deterministic cuBLAS workspace option and PyTorch's deterministic-algorithm behavior. [NVIDIA cuBLAS](https://docs.nvidia.com/cuda/cublas/), [PyTorch deterministic algorithms](https://docs.pytorch.org/docs/main/generated/torch.use_deterministic_algorithms.html).
