import json

from boss_agent_cli.web import RecruiterWebController


def _write_reply(controller: RecruiterWebController, filename: str, *, record_id: str, created_at: str, evaluation_id: str = "eval_1") -> None:
	path = controller.store.replies_dir / filename
	path.write_text(json.dumps({
		"id": record_id,
		"created_at": created_at,
		"evaluation_id": evaluation_id,
		"intent": "acknowledge",
		"draft": {"reply": record_id},
	}), encoding="utf-8")


def test_replies_sort_by_persisted_timestamp_not_random_filename_suffix(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	# Filenames deliberately disagree with chronological order inside the same second.
	_write_reply(
		controller,
		"reply_20260810T100000Z_zzzzzzzz.json",
		record_id="reply_a",
		created_at="2026-08-10T10:00:00.100000+00:00",
	)
	_write_reply(
		controller,
		"reply_20260810T100000Z_aaaaaaaa.json",
		record_id="reply_b",
		created_at="2026-08-10T18:00:00.200000+08:00",
	)
	_write_reply(
		controller,
		"reply_20260810T100000Z_mmmmmmmm.json",
		record_id="reply_c",
		created_at="2026-08-10T10:00:00.150000Z",
	)

	assert [item["id"] for item in controller.replies(limit=3)] == ["reply_b", "reply_c", "reply_a"]
	assert [item["id"] for item in controller.replies(limit=2)] == ["reply_b", "reply_c"]


def test_replies_filter_before_selecting_newest_limit(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	_write_reply(
		controller,
		"reply_20260810T100000Z_a.json",
		record_id="reply_a",
		created_at="2026-08-10T10:00:00+00:00",
		evaluation_id="eval_target",
	)
	_write_reply(
		controller,
		"reply_20260810T110000Z_b.json",
		record_id="reply_b",
		created_at="2026-08-10T11:00:00+00:00",
		evaluation_id="eval_other",
	)
	_write_reply(
		controller,
		"reply_20260810T120000Z_c.json",
		record_id="reply_c",
		created_at="2026-08-10T12:00:00+00:00",
		evaluation_id="eval_target",
	)

	assert [item["id"] for item in controller.replies(evaluation_id="eval_target", limit=1)] == ["reply_c"]
