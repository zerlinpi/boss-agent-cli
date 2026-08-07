from unittest.mock import MagicMock, patch

import boss_agent_cli.ai.service as service_module


def test_shared_ai_client_is_lazy_reused_and_closed() -> None:
	service_module._close_shared_client()
	client = MagicMock()
	with patch("boss_agent_cli.ai.service.httpx.Client", return_value=client) as constructor:
		first = service_module._shared_client()
		second = service_module._shared_client()

	assert first is client
	assert second is client
	constructor.assert_called_once_with()

	service_module._close_shared_client()
	client.close.assert_called_once_with()


def test_shared_ai_client_can_be_recreated_after_close() -> None:
	service_module._close_shared_client()
	first = MagicMock()
	second = MagicMock()
	with patch("boss_agent_cli.ai.service.httpx.Client", side_effect=[first, second]) as constructor:
		assert service_module._shared_client() is first
		service_module._close_shared_client()
		assert service_module._shared_client() is second

	assert constructor.call_count == 2
	first.close.assert_called_once_with()
	service_module._close_shared_client()
	second.close.assert_called_once_with()
