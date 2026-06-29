import sys
import pytest
from unittest.mock import patch
from pathlib import Path
import typer

from cli.contractpulse import _export_pdf

def test_export_pdf_missing_reportlab():
    with patch.dict(sys.modules, {'reportlab.lib.pagesizes': None, 'reportlab': None}):
        with patch("cli.contractpulse.console.print") as mock_print:
            with pytest.raises(typer.Exit) as exc_info:
                _export_pdf("job_123", Path("output.pdf"))

            assert exc_info.value.exit_code == 1
            mock_print.assert_any_call("[red]reportlab is required for PDF export.[/]")
