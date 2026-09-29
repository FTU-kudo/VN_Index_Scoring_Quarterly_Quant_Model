from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_workbook_generator_has_no_fixed_24_quarter_input_window():
    source = (ROOT / "generate_english_master_workbook.py").read_text(encoding="utf-8")
    assert 'Expected the complete 24-quarter history' not in source
    assert 'A5:A28' not in source
    assert 'style_table(ws, 5, 28' not in source


def test_workbook_verifier_uses_workbook_row_count():
    source = (ROOT / "verify_workbook_accuracy.py").read_text(encoding="utf-8")
    assert 'last_row = workbook["02_Market_Inputs"].max_row' in source
    assert 'require_formula_range(audit, workbook["03_Factor_SubScores"], 5, 28' not in source
