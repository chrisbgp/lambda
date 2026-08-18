import math
import unittest

from options_scanner import black_scholes_delta, option_lambda, parse_args


class CalculationTests(unittest.TestCase):
    def test_at_the_money_call_delta(self):
        delta = black_scholes_delta(100, 100, 1, 0.2, 0.05, 0, "call")
        self.assertAlmostEqual(delta, 0.6368, places=4)

    def test_put_call_delta_relationship(self):
        call = black_scholes_delta(100, 110, 2, 0.3, 0.04, 0.02, "call")
        put = black_scholes_delta(100, 110, 2, 0.3, 0.04, 0.02, "put")
        self.assertAlmostEqual(call - put, math.exp(-0.02 * 2), places=10)

    def test_lambda(self):
        self.assertEqual(option_lambda(0.5, 100, 10), 5)

    def test_default_duration(self):
        self.assertEqual(parse_args([]).min_days, 365)


if __name__ == "__main__":
    unittest.main()
