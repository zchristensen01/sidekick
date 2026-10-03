from typer.testing import CliRunner

from scout.cli import app

runner = CliRunner()

COMMANDS = ["doctor", "refresh", "watch", "report", "review", "draft-traits", "record", "postgame"]


def test_help_lists_every_command():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in COMMANDS:
        assert command in result.output


def test_report_role_option_is_checked():
    bad = runner.invoke(app, ["report", "--file", "x.yaml", "--role", "adc"])
    assert bad.exit_code == 2 and "adc" in bad.output


def test_report_explains_a_missing_game_file(scout_home):
    result = runner.invoke(app, ["report", "--file", "nope.yaml", "--role", "support"])
    assert result.exit_code == 1 and "nope.yaml" in result.output


def test_doctor_runs_without_crashing():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code in (0, 1)  # 1 = problems found (e.g. no config.yaml yet)
    assert "Python" in result.output
