"""Chunking contracts use synthetic prose and table cells, not vendor text."""

import unittest
from copy import deepcopy

from app.ingestion.chunking import chunk_document

DOCUMENT_KEY = "SYNTHETIC@A:" + "0" * 64


def text(value, label="text", **extra):
    return {"text": value, "label": label, "children": [], **extra}


def cell(value, row, column, *, header=False, row_span=1, col_span=1):
    return {"text": value, "column_header": header,
            "start_row_offset_idx": row, "end_row_offset_idx": row + row_span,
            "start_col_offset_idx": column, "end_col_offset_idx": column + col_span}


def headers():
    return [cell(value, 0, column, header=True)
            for column, value in enumerate(("编码（hex）", "故障/辅助代码", "原因", "措施"))]


def table(cells, pages=(7,)):
    return {"label": "table", "children": [], "prov": [{"page_no": page} for page in pages],
            "data": {"num_rows": max((c["end_row_offset_idx"] for c in cells), default=0),
                     "num_cols": max((c["end_col_offset_idx"] for c in cells), default=0),
                     "table_cells": cells}}


def document(*, texts=(), tables=(), groups=(), pictures=(), order=()):
    result = {"body": {"children": [{"$ref": ref} for ref in order]}}
    for name, nodes in (("texts", texts), ("tables", tables), ("groups", groups), ("pictures", pictures)):
        result[name] = [{**node, "self_ref": f"#/{name}/{i}"} for i, node in enumerate(nodes)]
    return result


def chunks(doc):
    return chunk_document(doc, DOCUMENT_KEY)


class SectionChunkTests(unittest.TestCase):
    def test_body_order_and_nested_lists_are_preserved(self):
        doc = document(texts=[text("second"), text("first"), text("step", "list_item", marker="1.")],
                       groups=[{"label": "list", "children": [{"$ref": "#/texts/2"}]}],
                       order=("#/texts/1", "#/groups/0", "#/texts/0"))
        original = deepcopy(doc)
        result = chunks(doc)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "first\n1. step\nsecond")
        self.assertEqual(result[0]["source_refs"], ["#/texts/1", "#/texts/2", "#/texts/0"])
        self.assertEqual(result[0]["document_key"], DOCUMENT_KEY)
        self.assertEqual(doc, original)

    def test_heading_levels_form_context_and_siblings_split(self):
        doc = document(texts=[text("Parent", "section_header", level=1), text("intro"),
                              text("Child", "section_header", level=2), text("detail"),
                              text("Next", "section_header", level=1), text("end")],
                       order=tuple(f"#/texts/{i}" for i in range(6)))
        result = chunks(doc)
        self.assertEqual([c["section"] for c in result], [["Parent"], ["Parent", "Child"], ["Next"]])
        self.assertEqual(result[1]["heading_refs"], ["#/texts/0", "#/texts/2"])
        self.assertEqual(result[1]["text"], "Parent\nChild\ndetail")

    def test_warning_headings_icons_conditions_and_steps_stay_together(self):
        for warning in ("警告！", "注意", "危险:"):
            with self.subTest(warning=warning):
                doc = document(texts=[text("Maintenance", "section_header", level=1), text("intro"),
                                      text(warning, "section_header", level=1), text("condition"),
                                      text("action", "list_item", marker="1.")],
                               pictures=[{"label": "picture", "children": []}],
                               order=("#/texts/0", "#/texts/1", "#/pictures/0", "#/texts/2",
                                      "#/texts/3", "#/texts/4"))
                result = chunks(doc)
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]["section"], ["Maintenance"])
                self.assertEqual(result[0]["text"], f"Maintenance\nintro\n{warning}\ncondition\n1. action")
                self.assertIn("#/pictures/0", result[0]["source_refs"])

    def test_page_headers_do_not_split_continuing_prose(self):
        doc = document(texts=[text("first"), text("page 8", "page_header"),
                              text("continued"), text("8", "page_footer")],
                       order=tuple(f"#/texts/{i}" for i in range(4)))
        self.assertEqual([c["text"] for c in chunks(doc)], ["first\ncontinued"])

    def test_table_boundary_preserves_interleaving_and_heading_context(self):
        doc = document(texts=[text("Section", "section_header", level=1), text("before"), text("after")],
                       tables=[table([cell("Value", 0, 0, header=True), cell("plain", 1, 0)])],
                       order=("#/texts/0", "#/texts/1", "#/tables/0", "#/texts/2"))
        result = chunks(doc)
        self.assertEqual([c["chunk_type"] for c in result], ["section", "table", "section"])
        self.assertEqual([c["section"] for c in result], [["Section"]] * 3)
        self.assertTrue(result[0]["text"].endswith("before"))
        self.assertTrue(result[-1]["text"].endswith("after"))

    def test_empty_input_does_not_emit_empty_chunks(self):
        self.assertEqual(chunks({}), [])
        self.assertEqual(chunks(document(tables=[table([])], order=("#/tables/0",))), [])


class SafetyChunkTests(unittest.TestCase):
    def test_explicit_labels_keep_original_text_and_do_not_become_section_headings(self):
        for word, label in (("警告", "warning"), ("注意", "caution"), ("危险", "danger")):
            for value in (word, f" {word} ：合成条件", f"{word}！", f"{word}\n合成条件"):
                for node_label in ("section_header", "text"):
                    with self.subTest(value=value, node_label=node_label):
                        doc = document(texts=[text("Parent", "section_header"), text(value, node_label),
                                              text("合成步骤", "list_item", marker="1.")],
                                       order=("#/texts/0", "#/texts/1", "#/texts/2"))
                        original = deepcopy(doc)
                        result = chunks(doc)
                        self.assertEqual(len(result), 1)
                        self.assertEqual(result[0]["safety_labels"], [label])
                        self.assertEqual(result[0]["section"], ["Parent"])
                        self.assertIn(value, result[0]["text"])
                        self.assertIn("1. 合成步骤", result[0]["text"])
                        self.assertEqual(doc, original)

    def test_mentions_and_similar_words_are_not_labels(self):
        for value in ("过热警告和故障", "注意事项", "危险因素分析", "请注意条件", "警告码 0001", "DANGER"):
            with self.subTest(value=value):
                doc = document(texts=[text(value, "section_header"), text("合成正文")],
                               order=("#/texts/0", "#/texts/1"))
                result = chunks(doc)[0]
                self.assertEqual(result["safety_labels"], [])
                self.assertEqual(result["section"], [value])

    def test_safety_conditions_tables_and_following_steps_remain_one_block(self):
        cells = headers() + [cell("00A1", 1, 0), cell("合成措施一", 1, 3),
                             cell("00B2", 2, 0), cell("合成措施二", 2, 3)]
        doc = document(texts=[text("合成前置条件"), text("警告：合成限制", "section_header"),
                              text("合成后置条件"), text("合成步骤", "list_item", marker="2.")],
                       tables=[table(cells)], pictures=[{"label": "picture", "children": []}],
                       order=("#/texts/0", "#/pictures/0", "#/texts/1", "#/tables/0", "#/texts/2", "#/texts/3"))
        original = deepcopy(doc)
        result = chunks(doc)
        self.assertEqual(len(result), 1)
        chunk = result[0]
        self.assertEqual(chunk["safety_labels"], ["warning"])
        self.assertEqual([c["normalized_code"] for c in chunk["fault_codes"]], ["00A1", "00B2"])
        self.assertTrue(chunk["text"].startswith("合成前置条件\n警告：合成限制"))
        self.assertTrue(chunk["text"].endswith("合成后置条件\n2. 合成步骤"))
        self.assertIn("合成措施一", chunk["text"])
        self.assertIn("合成措施二", chunk["text"])
        self.assertIn("#/pictures/0", chunk["source_refs"])
        for index in range(len(cells)):
            self.assertIn(f"#/tables/0/data/table_cells/{index}", chunk["source_refs"])
        self.assertNotIn("table_ref", chunk)
        self.assertEqual(doc, original)

    def test_label_in_table_cell_preserves_all_rows_and_surrounding_condition(self):
        cells = headers() + [cell("00A1", 1, 0), cell("危险！合成措施", 1, 3), cell("00B2", 2, 0)]
        doc = document(texts=[text("合成条件"), text("合成结尾")], tables=[table(cells)],
                       order=("#/texts/0", "#/tables/0", "#/texts/1"))
        chunk, = chunks(doc)
        self.assertEqual(chunk["safety_labels"], ["danger"])
        self.assertIn("00B2", chunk["text"])
        self.assertTrue(chunk["text"].startswith("合成条件\n"))
        self.assertTrue(chunk["text"].endswith("\n合成结尾"))

    def test_signal_after_table_keeps_preceding_conditions_in_the_same_section(self):
        doc = document(texts=[text("合成前置条件"), text("注意！"), text("合成后续限制")],
                       tables=[table([cell("合成表中条件", 0, 0)])],
                       order=("#/texts/0", "#/tables/0", "#/texts/1", "#/texts/2"))
        chunk, = chunks(doc)
        self.assertEqual(chunk["safety_labels"], ["caution"])
        self.assertEqual(chunk["text"], "合成前置条件\n合成表中条件\n注意！\n合成后续限制")

    def test_multiple_labels_are_sorted_unique_and_preserve_every_signal(self):
        doc = document(texts=[text("警告！"), text("合成条件\n注意：合成补充"), text("危险：合成限制"),
                              text("警告！"), text("合成操作")], order=tuple(f"#/texts/{i}" for i in range(5)))
        chunk, = chunks(doc)
        self.assertEqual(chunk["safety_labels"], ["caution", "danger", "warning"])
        self.assertEqual(chunk["text"].count("警告！"), 2)
        self.assertEqual(len(chunk["source_refs"]), 5)

    def test_normal_heading_ends_safety_context_without_leaking_labels(self):
        doc = document(texts=[text("警告！", "section_header"), text("合成安全条件"),
                              text("下一章节", "section_header"), text("普通正文")],
                       tables=[table([cell("普通表", 0, 0)])],
                       order=("#/texts/0", "#/texts/1", "#/texts/2", "#/texts/3", "#/tables/0"))
        result = chunks(doc)
        self.assertEqual([c["safety_labels"] for c in result], [["warning"], [], []])
        self.assertNotIn("合成安全条件", result[-1]["text"])

    def test_page_headers_do_not_break_label_condition_and_steps(self):
        doc = document(texts=[text("注意！", "section_header"), text("合成条件"), text("页眉", "page_header"),
                              text("步骤", "list_item", marker="1."), text("页脚", "page_footer")],
                       order=tuple(f"#/texts/{i}" for i in range(5)))
        chunk, = chunks(doc)
        self.assertEqual(chunk["text"], "注意！\n合成条件\n1. 步骤")
        self.assertEqual(chunk["safety_labels"], ["caution"])

    def test_isolated_label_is_retained_without_inventing_instructions(self):
        chunk, = chunks(document(texts=[text("危险！", "section_header")], order=("#/texts/0",)))
        self.assertEqual(chunk["text"], "危险！")
        self.assertEqual(chunk["safety_labels"], ["danger"])


class FaultRowChunkTests(unittest.TestCase):
    def test_cause_and_action_share_one_chunk_per_primary_code(self):
        cells = headers() + [cell("00a1", 1, 0), cell("name", 1, 1),
                             cell("cause one", 1, 2), cell("action one", 1, 3),
                             cell("00b2", 2, 0), cell("cause two", 2, 2), cell("action two", 2, 3)]
        doc = document(tables=[table(cells)], order=("#/tables/0",))
        result = chunks(doc)
        self.assertEqual([c["chunk_type"] for c in result], ["fault_rows", "fault_rows"])
        self.assertEqual([c["row_range"] for c in result], [[1, 2], [2, 3]])
        for index, word in enumerate(("one", "two")):
            self.assertIn(f"cause {word}", result[index]["text"])
            self.assertIn(f"action {word}", result[index]["text"])
        self.assertEqual(result[0]["fault_codes"][0]["raw_code"], "00a1")
        self.assertEqual(result[0]["fault_codes"][0]["normalized_code"], "00A1")

    def test_auxiliary_rows_and_nine_row_shared_action_stay_with_primary(self):
        cells = headers() + [cell("00A1", 1, 0), cell("main cause", 1, 2),
                             cell("shared action", 1, 3, row_span=9)]
        for row in range(2, 10):
            cells.extend([cell(f"{row:04}", row, 1), cell(f"aux cause {row}", row, 2)])
        cells.extend([cell("00B2", 10, 0), cell("next cause", 10, 2), cell("next action", 10, 3)])
        result = chunks(document(tables=[table(cells)], order=("#/tables/0",)))
        self.assertEqual([c["row_range"] for c in result], [[1, 10], [10, 11]])
        self.assertEqual(result[0]["text"].count("shared action"), 1)
        self.assertIn("aux cause 9", result[0]["text"])
        self.assertNotIn("shared action", result[1]["text"])
        self.assertEqual(len(result[0]["fault_codes"]), 1)

    def test_merged_cells_are_complete_in_each_intersecting_group(self):
        cells = headers() + [cell("00A1", 1, 0), cell("00B2", 2, 0),
                             cell("shared cause", 1, 1, row_span=2, col_span=2),
                             cell("shared action", 1, 3, row_span=2)]
        result = chunks(document(tables=[table(cells)], order=("#/tables/0",)))
        for chunk in result:
            self.assertIn("shared cause", chunk["text"])
            self.assertIn("shared action", chunk["text"])
            self.assertIn("#/tables/0/data/table_cells/7", chunk["source_refs"])

    def test_invalid_primary_starts_a_separate_unclassified_group(self):
        cells = headers() + [cell("00A1", 1, 0), cell("first", 1, 2),
                             cell("42\nF1", 2, 0), cell("unclassified", 2, 2),
                             cell("0001", 3, 1), cell("auxiliary", 3, 2), cell("00B2", 4, 0)]
        result = chunks(document(tables=[table(cells)], order=("#/tables/0",)))
        self.assertEqual([c["chunk_type"] for c in result], ["fault_rows", "table_rows", "fault_rows"])
        self.assertEqual(result[1]["fault_codes"], [])
        self.assertNotIn("unclassified", result[0]["text"])
        self.assertIn("42\nF1", result[1]["text"])
        self.assertIn("auxiliary", result[1]["text"])

    def test_rows_before_first_primary_are_retained_without_inheriting_a_code(self):
        cells = headers() + [cell("unattached", 1, 2), cell("00A1", 2, 0), cell("known", 2, 2)]
        result = chunks(document(tables=[table(cells)], order=("#/tables/0",)))
        self.assertEqual(result[0]["chunk_type"], "table_rows")
        self.assertEqual(result[0]["fault_codes"], [])
        self.assertIn("unattached", result[0]["text"])
        self.assertNotIn("unattached", result[1]["text"])

    def test_unrecognized_tables_are_kept_whole_and_separate(self):
        plain = table([cell("Parameter", 0, 0, header=True), cell("2310", 1, 0), cell("other", 2, 0)])
        doc = document(tables=[plain, table([cell("continuation", 0, 0)])],
                       order=("#/tables/0", "#/tables/1"))
        result = chunks(doc)
        self.assertEqual([c["chunk_type"] for c in result], ["table", "table"])
        self.assertIn("other", result[0]["text"])
        self.assertEqual(result[1]["table_ref"], "#/tables/1")

    def test_table_provenance_and_cell_references_remain_resolvable(self):
        doc = document(tables=[table(headers() + [cell("00A1", 1, 0), cell("cause", 1, 2)], pages=(7, 8))],
                       order=("#/tables/0",))
        original = deepcopy(doc)
        for chunk in chunks(doc):
            for ref in chunk["source_refs"]:
                target = doc
                for part in ref[2:].split("/"):
                    target = target[int(part)] if isinstance(target, list) else target[part]
                self.assertIn("text", target)
        self.assertEqual(doc, original)
        self.assertEqual(doc["tables"][0]["prov"], [{"page_no": 7}, {"page_no": 8}])


if __name__ == "__main__":
    unittest.main()
