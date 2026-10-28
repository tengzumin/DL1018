#!/usr/bin/env python3
"""Run the CPU-only synthetic check; this does not open data or train."""
from train_mlp15_c5_full72_v1 import self_check

if __name__ == "__main__":
    self_check()
