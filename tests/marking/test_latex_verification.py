from amath_bot.marking.latex_verification import verify_latex_lines


def test_parseable_equivalent_transition_is_verified() -> None:
    result = verify_latex_lines(
        [
            {"id": 1, "latex": r"\frac{2x}{2}"},
            {"id": 2, "latex": "x"},
        ]
    )

    assert result[0] == {"line_id": 1, "parse_status": "parsed"}
    assert result[1]["parse_status"] == "parsed"
    assert result[1]["transition_status"] == "equivalent"


def test_parser_failure_marks_line_unverified_without_rejecting_transcription() -> None:
    result = verify_latex_lines(
        [
            {"id": 1, "latex": "x & y"},
            {"id": 2, "latex": "x"},
        ]
    )

    assert len(result) == 2
    assert result[0]["parse_status"] == "unverified"
    assert result[0]["parse_error"]
    assert result[1]["parse_status"] == "parsed"
    assert result[1]["transition_status"] == "unverified"
