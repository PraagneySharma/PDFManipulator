"""Tests with generated PDFs: each page has a distinctive width to verify order."""

import tempfile
from pathlib import Path
import unittest

from pypdf import PdfReader, PdfWriter

from app import DuplexError, merge_duplex, page_counts


class DuplexMergeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.fronts = self.directory / "fronts.pdf"
        self.backs = self.directory / "backs.pdf"
        self.output = self.directory / "merged.pdf"

    def create_pdf(self, filename, page_numbers):
        writer = PdfWriter()
        for number in page_numbers:
            writer.add_blank_page(width=600 + number, height=800)
        with open(filename, "wb") as file:
            writer.write(file)

    def output_order(self):
        return [int(page.mediabox.width) - 600 for page in PdfReader(self.output).pages]

    def test_even_pages(self):
        self.create_pdf(self.fronts, [1, 3, 5])
        self.create_pdf(self.backs, [6, 4, 2])
        count = merge_duplex(self.fronts, self.backs, self.output)
        self.assertEqual(count, 6)
        self.assertEqual(self.output_order(), [1, 2, 3, 4, 5, 6])

    def test_odd_pages(self):
        self.create_pdf(self.fronts, [1, 3, 5])
        self.create_pdf(self.backs, [4, 2])
        self.assertEqual(page_counts(self.fronts, self.backs), (3, 2))
        self.assertEqual(merge_duplex(self.fronts, self.backs, self.output), 5)
        self.assertEqual(self.output_order(), [1, 2, 3, 4, 5])

    def test_ten_pages_reverse_is_default(self):
        self.create_pdf(self.fronts, [1, 3, 5, 7, 9])
        self.create_pdf(self.backs, [10, 8, 6, 4, 2])
        merge_duplex(self.fronts, self.backs, self.output)
        self.assertEqual(self.output_order(), list(range(1, 11)))

    def test_ascending_back_pages_are_opt_in(self):
        self.create_pdf(self.fronts, [1, 3, 5])
        self.create_pdf(self.backs, [2, 4, 6])
        merge_duplex(self.fronts, self.backs, self.output, reverse_backs=False)
        self.assertEqual(self.output_order(), [1, 2, 3, 4, 5, 6])

    def test_nine_pages_with_first_blank_back(self):
        self.create_pdf(self.fronts, [1, 3, 5, 7, 9])
        self.create_pdf(self.backs, [0, 8, 6, 4, 2])
        merge_duplex(self.fronts, self.backs, self.output, skip_first_back=True)
        self.assertEqual(self.output_order(), list(range(1, 10)))

    def test_skip_blank_rejects_missing_back(self):
        self.create_pdf(self.fronts, [1, 3, 5])
        self.create_pdf(self.backs, [4, 2])
        with self.assertRaisesRegex(DuplexError, "the same page count"):
            merge_duplex(self.fronts, self.backs, self.output, skip_first_back=True)
        self.assertFalse(self.output.exists())

    def test_rotate_back_pages_only(self):
        self.create_pdf(self.fronts, [1, 3])
        self.create_pdf(self.backs, [4, 2])
        merge_duplex(self.fronts, self.backs, self.output, rotate_backs=True)
        pages = PdfReader(self.output).pages
        self.assertEqual([page.rotation for page in pages], [0, 180, 0, 180])

    def test_one_page_without_backs(self):
        self.create_pdf(self.fronts, [1])
        merge_duplex(self.fronts, None, self.output)
        self.assertEqual(self.output_order(), [1])

    def test_invalid_count_does_not_create_output(self):
        self.create_pdf(self.fronts, [1, 3, 5])
        self.create_pdf(self.backs, [2])
        with self.assertRaisesRegex(DuplexError, "Page counts do not match"):
            merge_duplex(self.fronts, self.backs, self.output)
        self.assertFalse(self.output.exists())

    def test_output_cannot_overwrite_fronts(self):
        self.create_pdf(self.fronts, [1, 3])
        self.create_pdf(self.backs, [2, 4])
        with self.assertRaisesRegex(DuplexError, "originals are not overwritten"):
            merge_duplex(self.fronts, self.backs, self.fronts)

    def test_same_input_files_rejected(self):
        self.create_pdf(self.fronts, [1, 3])
        with self.assertRaisesRegex(DuplexError, "two different files"):
            merge_duplex(self.fronts, self.fronts, self.output)


if __name__ == "__main__":
    unittest.main()
