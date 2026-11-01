"""No-network regression tests: bounded Helius pagination and budget reservation."""
import unittest

from research.smart_money_lab.paper_copy_next import (
    _bounded_wallet_history, _ensure_new_budget,
    UnverifiableHistoryGap, MAX_HISTORY_PAGES,
)


def rows(prefix, count, timestamp):
    return [{"signature": f"{prefix}-{i}", "timestamp": timestamp}
            for i in range(count)]


class FakeHelius:
    def __init__(self, pages):
        self.pages = pages
        self.calls = 0
        self.befores = []

    def transactions(self, wallet, *, before="", limit=100):
        assert wallet == "test_wallet"
        assert limit == 100
        self.befores.append(before)
        if self.calls:
            assert before == self.pages[self.calls - 1][-1]["signature"]
        page = self.pages[self.calls]
        self.calls += 1
        return page


class BoundedHistoryTests(unittest.TestCase):
    def test_short_first_page_no_pagination(self):
        h = FakeHelius([rows("first", 30, 1100)])
        raw, count = _bounded_wallet_history(h, "test_wallet", cutoff=1000)
        self.assertEqual((len(raw), count, h.calls), (30, 1, 1))

    def test_full_page_already_has_strict_overlap(self):
        a = rows("first", 99, 1100) + rows("old", 1, 999)
        h = FakeHelius([a])
        raw, count = _bounded_wallet_history(h, "test_wallet", cutoff=1000)
        self.assertEqual((len(raw), count), (100, 1))
        self.assertEqual(h.calls, 1)

    def test_fetches_page_two_until_strict_overlap(self):
        h = FakeHelius([rows("first", 100, 1100),
                        rows("second", 100, 999)])
        raw, count = _bounded_wallet_history(h, "test_wallet", cutoff=1000)
        self.assertEqual((len(raw), count, h.calls), (200, 2, 2))

    def test_equal_second_is_not_proof_of_overlap(self):
        h = FakeHelius([rows("first", 100, 1100),
                        rows("equal", 100, 1000),
                        rows("older", 14, 999)])
        raw, count = _bounded_wallet_history(h, "test_wallet", cutoff=1000)
        self.assertEqual((len(raw), count), (214, 3))

    def test_hard_stop_when_more_than_three_pages_are_required(self):
        h = FakeHelius([rows(f"p{i}", 100, 1100) for i in range(3)])
        with self.assertRaises(UnverifiableHistoryGap):
            _bounded_wallet_history(h, "test_wallet", cutoff=1000)
        self.assertEqual(h.calls, MAX_HISTORY_PAGES)

    def test_repeated_signature_across_pages_refused(self):
        first = rows("first", 100, 1100)
        second = rows("second", 15, 999)
        second[0]["signature"] = first[10]["signature"]
        h = FakeHelius([first, second])
        with self.assertRaises(UnverifiableHistoryGap):
            _bounded_wallet_history(h, "test_wallet", cutoff=1000)

    def test_invalid_full_page_timestamp_refused(self):
        page = rows("first", 100, 1100)
        page[4]["timestamp"] = None
        h = FakeHelius([page])
        with self.assertRaises(UnverifiableHistoryGap):
            _bounded_wallet_history(h, "test_wallet", cutoff=1000)

    def test_budget_reserves_worst_case_and_retries(self):
        result = _ensure_new_budget(300, 6, 6, 2180)
        self.assertEqual(result["estimated_calls"], 432)
        self.assertEqual(result["worst_case_calls"], 1296)
        self.assertEqual(result["minimum_remaining_calls"], 1568)
        with self.assertRaises(ValueError):
            _ensure_new_budget(300, 6, 6, 1567)


if __name__ == "__main__":
    unittest.main()
