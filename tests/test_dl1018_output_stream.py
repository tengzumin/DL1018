import sys
import unittest
from pathlib import Path

import run_dl1018


class BrokenStdout:
    encoding = "utf-8"

    def write(self, _text):
        raise OSError(22, "Invalid argument")

    def flush(self):
        pass


class OutputStreamTest(unittest.TestCase):
    def test_child_pipe_is_drained_after_console_write_fails(self):
        original_stdout = sys.stdout
        try:
            sys.stdout = BrokenStdout()
            run_dl1018._stream_process(
                [sys.executable, "-c", "import sys; sys.stdout.write('x' * 1048576 + '\\n')"],
                Path(__file__).resolve().parents[1],
                "output-stream regression check",
            )
        finally:
            sys.stdout = original_stdout


if __name__ == "__main__":
    unittest.main()
