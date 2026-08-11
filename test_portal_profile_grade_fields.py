from dashboard.portal.classroom_rules import expected_grade_levels, get_classroom_levels


def test_profile_grade_inputs_use_the_same_levels_as_backend_validation():
    for jenjang in ("TK", "KB", "SPS", "TPA", "SD", "SMP", "SMA", "SMK", "SKB", "PKBM", "SLB"):
        rendered_levels = [
            int(level["code"])
            for level in get_classroom_levels(jenjang, for_profile=True)
        ]
        assert rendered_levels == expected_grade_levels(jenjang)


def test_skb_and_pkbm_profile_show_paket_fields():
    assert expected_grade_levels("SKB") == [-21, -22, -23]
    assert expected_grade_levels("PKBM") == [-21, -22, -23]
