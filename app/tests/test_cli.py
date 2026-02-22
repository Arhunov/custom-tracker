import pytest
from typer.testing import CliRunner
from app.cli import app
from unittest.mock import patch, MagicMock
import json

runner = CliRunner()

def test_list_modules():
    mock_modules = [
        {"id": 1, "name": "module1", "schema": {"type": "object", "properties": {"value": {"type": "integer"}}}},
        {"id": 2, "name": "module2", "schema": {"type": "object", "properties": {"status": {"type": "string"}}}},
    ]

    with patch("httpx.Client") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.get.return_value = MagicMock(status_code=200, json=lambda: mock_modules)

        result = runner.invoke(app, ["list-modules"])
        assert result.exit_code == 0
        assert "Modules" in result.stdout
        assert "module1" in result.stdout
        assert "module2" in result.stdout
        assert "value" in result.stdout # part of schema

def test_create_module_with_file(tmp_path):
    module_def = {
        "name": "test_module",
        "schema": {"type": "object", "properties": {"foo": {"type": "string"}}}
    }
    file_path = tmp_path / "module.json"
    file_path.write_text(json.dumps(module_def))

    with patch("httpx.Client") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.post.return_value = MagicMock(status_code=201, json=lambda: {"id": 1, **module_def})

        result = runner.invoke(app, ["create-module", "--file", str(file_path)])
        assert result.exit_code == 0
        assert "created successfully" in result.stdout

        # Verify call arguments
        mock_instance.post.assert_called_once()
        args, kwargs = mock_instance.post.call_args
        assert kwargs["json"]["name"] == "test_module"
        assert kwargs["json"]["schema"] == module_def["schema"]

def test_create_event_with_file(tmp_path):
    payload = {"foo": "bar"}
    file_path = tmp_path / "event.json"
    file_path.write_text(json.dumps(payload))

    with patch("httpx.Client") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.post.return_value = MagicMock(status_code=201, json=lambda: {"id": 1, "module_id": 1, "payload": payload})

        result = runner.invoke(app, ["create-event", "1", "--file", str(file_path)])
        assert result.exit_code == 0
        assert "created successfully" in result.stdout

        # Verify call arguments
        mock_instance.post.assert_called_once()
        args, kwargs = mock_instance.post.call_args
        assert kwargs["json"]["module_id"] == 1
        assert kwargs["json"]["payload"] == payload

def test_aggregate_table():
    mock_results = [
        {"group": {"day": "2023-01-01"}, "value": 10},
        {"group": {"day": "2023-01-02"}, "value": 20},
    ]

    with patch("httpx.Client") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.post.return_value = MagicMock(status_code=200, json=lambda: mock_results)

        result = runner.invoke(app, ["aggregate", "--group-by", "day"])
        assert result.exit_code == 0
        assert "Aggregation Results" in result.stdout
        assert "Day" in result.stdout
        assert "Value" in result.stdout
        assert "2023-01-01" in result.stdout
        assert "10" in result.stdout

def test_create_webhook():
    with patch("httpx.Client") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.post.return_value = MagicMock(status_code=201, json=lambda: {"id": 1, "url": "http://example.com", "module_id": None})

        result = runner.invoke(app, ["create-webhook", "http://example.com"])
        assert result.exit_code == 0
        assert "created successfully" in result.stdout

        mock_instance.post.assert_called_once()

def test_list_webhooks():
    mock_webhooks = [
        {"id": 1, "url": "http://example.com", "module_id": 1, "event_type": "event.created"}
    ]
    with patch("httpx.Client") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.get.return_value = MagicMock(status_code=200, json=lambda: mock_webhooks)

        result = runner.invoke(app, ["list-webhooks"])
        assert result.exit_code == 0
        assert "Webhooks" in result.stdout
        assert "http://example.com" in result.stdout

def test_delete_webhook():
    with patch("httpx.Client") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.delete.return_value = MagicMock(status_code=204)

        result = runner.invoke(app, ["delete-webhook", "1"])
        assert result.exit_code == 0
        assert "deleted successfully" in result.stdout
