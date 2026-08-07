import base64

import pytest

from boss_agent_cli.web import RecruiterWebController, WebConsoleError
from boss_agent_cli.web.upload_policy import MAX_LOCAL_BATCH_BYTES, _base64_decoded_size


def test_base64_size_estimate_accounts_for_padding() -> None:
	for raw in (b"a", b"ab", b"abc", b"abcd"):
		encoded = base64.b64encode(raw).decode("ascii")
		assert _base64_decoded_size(encoded) == len(raw)


def test_local_screen_rejects_oversized_batch_before_job_lookup_or_ai(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	# The encoded text does not need to contain a real resume: the batch policy must reject it
	# before document decoding, job lookup, or AI initialization.
	chunk_size = MAX_LOCAL_BATCH_BYTES // 2 + 1
	encoded = "A" * (((chunk_size + 2) // 3) * 4)
	payload = {
		"job_key": "missing-job",
		"documents": [
			{"name": "a.pdf", "content_base64": encoded},
			{"name": "b.pdf", "content_base64": encoded},
		],
	}

	with pytest.raises(WebConsoleError) as caught:
		controller.screen_local(payload)

	assert caught.value.code == "PAYLOAD_TOO_LARGE"
	assert caught.value.status == 413
	assert "40 MB" in str(caught.value)


def test_json_payload_size_contributes_to_batch_limit(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	large_text = "x" * (MAX_LOCAL_BATCH_BYTES // 2 + 1)
	payload = {
		"job_key": "missing-job",
		"documents": [
			{"name": "a.json", "payload": {"raw_text": large_text}},
			{"name": "b.json", "payload": {"raw_text": large_text}},
		],
	}

	with pytest.raises(WebConsoleError) as caught:
		controller.screen_local(payload)

	assert caught.value.code == "PAYLOAD_TOO_LARGE"
