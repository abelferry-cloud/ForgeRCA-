"""Conservative ABB fault-code recognition, without vendor text fixtures."""

import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError

from app.ingestion.fault_codes import extract_fault_codes
from app.schemas.fault_code import FaultCode


def cell(text, row, column, *, header=False, row_span=1, col_span=1):
    return {
        "text": text, "column_header": header,
        "start_row_offset_idx": row, "end_row_offset_idx": row + row_span,
        "start_col_offset_idx": column, "end_col_offset_idx": column + col_span,
    }


def table(cells, ref="#/tables/0"):
    return {"self_ref": ref, "data": {"table_cells": cells}}


def headers():
    return [cell("编码 （hex）", 0, 0, header=True), cell("故障/辅助代码", 0, 1, header=True)]


class FaultCodeTests(unittest.TestCase):
    def test_raw_spelling_is_preserved_and_normalized_as_text(self):
        for raw, normalized in (("0010", "0010"), ("42f1", "42F1"), ("\t00aF \n", "00AF"), ("A0b1", "A0B1")):
            with self.subTest(raw=raw):
                code = FaultCode.from_raw(raw)
                self.assertEqual(code.raw_code, raw)
                self.assertEqual(code.normalized_code, normalized)
                self.assertEqual(FaultCode.from_raw(normalized).normalized_code, normalized)

    def test_code_values_are_immutable(self):
        code = FaultCode.from_raw("0010")
        with self.assertRaises(FrozenInstanceError):
            code.raw_code = "changed"

    def test_non_strings_are_not_coerced(self):
        for raw in (2310, 42.1, None, True, b"2310"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                FaultCode.from_raw(raw)

    def test_non_codes_and_unapproved_repairs_are_rejected(self):
        for raw in (
            "", "   ", "010", "00010", "0x83", "0x2310", "31.21", "XXXYYYZZ",
            "42 F1", "42\nF1", "2310/2330", "42G1", "故障2310", "４２Ｆ１", "٤٢F١", "ﬀ01",
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                FaultCode.from_raw(raw)


class FaultCodeExtractionTests(unittest.TestCase):
    def test_only_primary_code_column_is_extracted_with_resolvable_refs(self):
        cells = headers() + [
            cell(" 00a1 ", 1, 0), cell("0001", 1, 1),
            cell("", 2, 0), cell("0002", 2, 1),
            cell("42f1", 3, 0), cell("31.21", 3, 2),
        ]
        document = {"texts": [{"text": "2310 0x83 31.21"}], "tables": [table(cells)]}
        original = deepcopy(document)
        found = extract_fault_codes(document)
        self.assertEqual(found, [
            {"raw_code": " 00a1 ", "normalized_code": "00A1", "cell_ref": "#/tables/0/data/table_cells/2"},
            {"raw_code": "42f1", "normalized_code": "42F1", "cell_ref": "#/tables/0/data/table_cells/6"},
        ])
        self.assertEqual(document, original)
        for occurrence in found:
            target = document
            for part in occurrence["cell_ref"][2:].split("/"):
                target = target[int(part)] if isinstance(target, list) else target[part]
            self.assertEqual(target["text"], occurrence["raw_code"])

    def test_regular_tables_and_unlabelled_continuations_are_not_guessed(self):
        for first, second in (("年份", "说明"), ("编码（hex）", "参数"), ("参数", "故障/辅助代码")):
            with self.subTest(first=first, second=second):
                document = {"tables": [table([
                    cell(first, 0, 0, header=True), cell(second, 0, 1, header=True), cell("2026", 1, 0),
                ])]}
                self.assertEqual(extract_fault_codes(document), [])
        self.assertEqual(extract_fault_codes({"tables": [table([cell("2310", 1, 0)])]}), [])
        self.assertEqual(extract_fault_codes({}), [])

    def test_header_pair_must_be_adjacent_on_the_same_row(self):
        for row, column in ((1, 1), (0, 2)):
            with self.subTest(row=row, column=column):
                cells = [cell("编码（hex）", 0, 0, header=True),
                         cell("故障/辅助代码", row, column, header=True), cell("2310", 2, 0)]
                self.assertEqual(extract_fault_codes({"tables": [table(cells)]}), [])

    def test_header_whitespace_and_ascii_parentheses_are_supported(self):
        cells = [cell("编码\n(HEX)", 0, 0, header=True),
                 cell("故障/辅助代码", 0, 1, header=True), cell("0010", 1, 0)]
        self.assertEqual(extract_fault_codes({"tables": [table(cells)]})[0]["normalized_code"], "0010")

    def test_repeated_occurrences_keep_separate_local_references(self):
        document = {"tables": [
            table(headers() + [cell("0010", 1, 0), cell("0010", 2, 0)]),
            table(headers() + [cell("0010", 1, 0)], ref="#/tables/1"),
        ]}
        found = extract_fault_codes(document)
        self.assertEqual([item["normalized_code"] for item in found], ["0010"] * 3)
        self.assertEqual(len({item["cell_ref"] for item in found}), 3)

    def test_cells_outside_header_column_or_before_header_are_ignored(self):
        cells = [cell("0010", 0, 0), cell("编码（hex）", 1, 0, header=True),
                 cell("故障/辅助代码", 1, 1, header=True), cell("0020", 2, 0, col_span=2),
                 cell("0030", 3, 0, row_span=2)]
        self.assertEqual([item["normalized_code"] for item in extract_fault_codes({"tables": [table(cells)]})],
                         ["0030"])

    def test_invalid_code_cells_stay_in_the_original_document(self):
        values = ("31.21", "0x83", "42\nF1", "42G1", "2310/2330", "")
        document = {"tables": [table(headers() + [cell(value, i + 1, 0) for i, value in enumerate(values)])]}
        original = deepcopy(document)
        self.assertEqual(extract_fault_codes(document), [])
        self.assertEqual(document, original)


if __name__ == "__main__":
    unittest.main()
