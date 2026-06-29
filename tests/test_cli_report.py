from unittest.mock import patch
from pathlib import Path
from typer.testing import CliRunner
import pytest

from cli.contractpulse import app

runner = CliRunner()

def test_report_terminal_output():
    with patch("cli.contractpulse._render_report") as mock_render:
        result = runner.invoke(app, ["report", "job_123"])
        assert result.exit_code == 0
        mock_render.assert_called_once_with("job_123")

def test_report_pdf_output_missing_save():
    result = runner.invoke(app, ["report", "job_123", "--output", "pdf"])
    assert result.exit_code == 1
    assert "--save <path> is required when using --output pdf" in result.stdout

def test_report_pdf_output_with_save():
    with patch("cli.contractpulse._export_pdf") as mock_export:
        result = runner.invoke(app, ["report", "job_123", "--output", "pdf", "--save", "output.pdf"])
        assert result.exit_code == 0
        mock_export.assert_called_once_with("job_123", Path("output.pdf"))
