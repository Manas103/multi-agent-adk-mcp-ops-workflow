from src.si_signoff.task_corpus import build_corpus


def test_corpus_is_128_tasks_in_4_equal_families():
    tasks = build_corpus()
    assert len(tasks) == 128
    families: dict[tuple, int] = {}
    for t in tasks:
        key = (t.has_package, t.interface["standard"])
        families[key] = families.get(key, 0) + 1
    assert families == {
        (False, "NRZ"): 32, (False, "PAM4"): 32, (True, "NRZ"): 32, (True, "PAM4"): 32,
    }


def test_corpus_is_deterministic_across_builds():
    a = build_corpus()
    b = build_corpus()
    assert [t.segments for t in a] == [t.segments for t in b]
    assert [t.cascade_intent for t in a] == [t.cascade_intent for t in b]


def test_package_tasks_carry_a_package_segment_first():
    tasks = build_corpus()
    for t in tasks:
        if t.has_package:
            assert t.segments[0]["role"] == "package"
            assert any(s["role"] == "board" for s in t.segments)
        else:
            assert all(s["role"] == "board" for s in t.segments)
