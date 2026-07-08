from unittest.mock import patch, MagicMock
from codeweave.config.model import get_chat_model

def test_get_chat_model_returns_chat_model():
    with patch("codeweave.config.model.init_chat_model") as mock_init:
        mock_instance = MagicMock()
        mock_init.return_value = mock_instance

        model = get_chat_model(temperature=0.5)

        mock_init.assert_called_once()
        call_kwargs = mock_init.call_args.kwargs
        assert call_kwargs["temperature"] == 0.5
        assert mock_instance == model

def test_get_chat_model_uses_settings():
    from codeweave.config.settings import Settings

    s = Settings(_env_file=None)
    with patch("codeweave.config.model.init_chat_model") as mock_init:
        mock_init.return_value = MagicMock()
        get_chat_model(settings=s)
        call_kwargs = mock_init.call_args.kwargs
        assert call_kwargs["model"] == s.model_name
