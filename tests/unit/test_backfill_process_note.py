from apps.worker.backfill_process_note import needs_rewrite

AUTO = "Automated checks, not an editor, approved this article for publication."


def test_policy_approved_article_with_the_old_note_is_rewritten() -> None:
    assert needs_rewrite("approved by policy", "An editor reviewed and approved it.", AUTO)


def test_editor_approved_or_already_fixed_articles_are_left_alone() -> None:
    assert not needs_rewrite("", "An editor reviewed and approved it.", AUTO)
    assert not needs_rewrite("approved by policy", AUTO, AUTO)
