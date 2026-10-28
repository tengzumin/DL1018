#!/usr/bin/env python3
"""Run the C5-only identity and CPU streaming toy checks; never trains."""
from train_gru_stream_c5_teacher_v1 import self_check


if __name__ == "__main__":
    self_check()
