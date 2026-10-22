"""Synthetic-only tests for R3 tilt-limiting event semantics."""

import unittest

import numpy as np

from rescore_round3 import PLANT_DT, TILT_TICKS, new_tilt_limited_mask, transition_time_vector


class TiltLimitedMaskTests(unittest.TestCase):
    def test_union_of_controls_covers_xy_events(self) -> None:
        xy = np.zeros(TILT_TICKS, dtype=np.uint8)
        b = np.zeros_like(xy)
        on = np.zeros_like(xy)
        off = np.zeros_like(xy)
        xy[[10, 20, 30]] = 1
        b[10] = 1
        on[20] = 1
        off[30] = 1

        self.assertEqual(int(np.count_nonzero(new_tilt_limited_mask(xy, b, on, off))), 0)

    def test_xy_only_event_is_new(self) -> None:
        xy = np.zeros(TILT_TICKS, dtype=np.uint8)
        b = np.zeros_like(xy)
        on = np.zeros_like(xy)
        off = np.zeros_like(xy)
        xy[1234] = 1

        new_events = new_tilt_limited_mask(xy, b, on, off)
        self.assertEqual(int(np.count_nonzero(new_events)), 1)
        self.assertTrue(new_events[1234])

    def test_wrong_length_fails_closed(self) -> None:
        valid = np.zeros(TILT_TICKS, dtype=np.uint8)
        with self.assertRaises(RuntimeError):
            new_tilt_limited_mask(valid[:-1], valid, valid, valid)

    def test_nonbinary_and_nonfinite_flags_fail_closed(self) -> None:
        valid = np.zeros(TILT_TICKS, dtype=np.uint8)
        nonbinary = valid.copy()
        nonbinary[1] = 2
        with self.assertRaises(RuntimeError):
            new_tilt_limited_mask(nonbinary, valid, valid, valid)

        nonfinite = valid.astype(float)
        nonfinite[2] = np.nan
        with self.assertRaises(RuntimeError):
            new_tilt_limited_mask(valid, valid, nonfinite, valid)


class TransitionTimeGridTests(unittest.TestCase):
    def test_canonical_plant_grid_passes(self) -> None:
        axis = np.arange(TILT_TICKS, dtype=float) * PLANT_DT
        np.testing.assert_array_equal(transition_time_vector(axis), axis)

    def test_nonuniform_middle_tick_fails_even_with_unchanged_endpoints(self) -> None:
        axis = np.arange(TILT_TICKS, dtype=float) * PLANT_DT
        axis[TILT_TICKS // 2] += 1e-6
        self.assertEqual(axis[0], 0.0)
        self.assertEqual(axis[-1], (TILT_TICKS - 1) * PLANT_DT)
        with self.assertRaises(RuntimeError):
            transition_time_vector(axis)

    def test_nonfinite_tick_fails(self) -> None:
        axis = np.arange(TILT_TICKS, dtype=float) * PLANT_DT
        axis[1] = np.nan
        with self.assertRaises(RuntimeError):
            transition_time_vector(axis)

    def test_wrong_length_and_wrong_step_fail(self) -> None:
        axis = np.arange(TILT_TICKS, dtype=float) * PLANT_DT
        with self.assertRaises(RuntimeError):
            transition_time_vector(axis[:-1])
        wrong_step = np.arange(TILT_TICKS, dtype=float) * 0.0011
        with self.assertRaises(RuntimeError):
            transition_time_vector(wrong_step)


if __name__ == "__main__":
    unittest.main()
