# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2021-2022 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
from argparse import Namespace
from unittest.mock import call, patch

import pytest
import yaml
from craft_cli import CraftError, ProvideHelpException, emit
from craft_providers import ProviderError

from rockcraft import cli, project
from rockcraft.errors import RockcraftError


@pytest.fixture
def lifecycle_pack_mock():
    """Mock for ui.pack."""
    patcher = patch("rockcraft.lifecycle.pack")
    yield patcher.start()
    patcher.stop()


@pytest.fixture
def lifecycle_init_mock():
    """Mock for ui.init."""
    patcher = patch("rockcraft.commands.init.init")
    yield patcher.start()
    patcher.stop()


def create_namespace(
    *, parts=None, shell=False, shell_after=False, debug=False
) -> Namespace:
    """Shortcut to create a Namespace object with the correct default values."""
    return Namespace(
        parts=parts or [], shell=shell, shell_after=shell_after, debug=debug
    )


@pytest.mark.parametrize("cmd", ["pull", "overlay", "build", "stage", "prime"])
def test_run_command(mocker, cmd):
    run_mock = mocker.patch("rockcraft.lifecycle.run")
    mock_ended_ok = mocker.spy(emit, "ended_ok")
    mocker.patch.object(sys, "argv", ["rockcraft", cmd])
    cli.run()

    assert run_mock.mock_calls == [call(cmd, create_namespace())]
    assert mock_ended_ok.mock_calls == [call()]


@pytest.mark.parametrize("cmd", ["pull", "overlay", "build", "stage", "prime"])
def test_run_command_parts(mocker, cmd):
    run_mock = mocker.patch("rockcraft.lifecycle.run")
    mock_ended_ok = mocker.spy(emit, "ended_ok")
    mocker.patch.object(sys, "argv", ["rockcraft", cmd, "part1", "part2"])
    cli.run()

    assert run_mock.mock_calls == [
        call(
            cmd,
            create_namespace(parts=["part1", "part2"]),
        )
    ]
    assert mock_ended_ok.mock_calls == [call()]


@pytest.mark.parametrize("cmd", ["pull", "overlay", "build", "stage", "prime"])
def test_run_command_shell(mocker, cmd):
    run_mock = mocker.patch("rockcraft.lifecycle.run")
    mock_ended_ok = mocker.spy(emit, "ended_ok")
    mocker.patch.object(sys, "argv", ["rockcraft", cmd, "--shell"])
    cli.run()

    assert run_mock.mock_calls == [call(cmd, create_namespace(shell=True))]
    assert mock_ended_ok.mock_calls == [call()]


@pytest.mark.parametrize("cmd", ["pull", "overlay", "build", "stage", "prime"])
def test_run_command_shell_after(mocker, cmd):
    run_mock = mocker.patch("rockcraft.lifecycle.run")
    mock_ended_ok = mocker.spy(emit, "ended_ok")
    mocker.patch.object(sys, "argv", ["rockcraft", cmd, "--shell-after"])
    cli.run()

    assert run_mock.mock_calls == [call(cmd, create_namespace(shell_after=True))]
    assert mock_ended_ok.mock_calls == [call()]


@pytest.mark.parametrize("cmd", ["pull", "overlay", "build", "stage", "prime"])
def test_run_command_debug(mocker, cmd):
    run_mock = mocker.patch("rockcraft.lifecycle.run")
    mock_ended_ok = mocker.spy(emit, "ended_ok")
    mocker.patch.object(sys, "argv", ["rockcraft", cmd, "--debug"])
    cli.run()

    assert run_mock.mock_calls == [call(cmd, create_namespace(debug=True))]
    assert mock_ended_ok.mock_calls == [call()]


@pytest.mark.parametrize("debug_opt", [True, False])
def test_run_pack(mocker, debug_opt):
    run_mock = mocker.patch("rockcraft.lifecycle.run")
    mock_ended_ok = mocker.spy(emit, "ended_ok")
    command_line = ["rockcraft", "pack"]
    if debug_opt:
        command_line.append("--debug")
    mocker.patch.object(sys, "argv", command_line)
    cli.run()

    assert run_mock.mock_calls == [call("pack", Namespace(debug=debug_opt))]
    assert mock_ended_ok.mock_calls == [call()]


def test_run_init(mocker, lifecycle_init_mock):
    mock_ended_ok = mocker.spy(emit, "ended_ok")
    mocker.patch.object(sys, "argv", ["rockcraft", "init"])
    cli.run()

    rock_project = project.Project.unmarshal(
        yaml.safe_load(
            # pylint: disable=W0212
            cli.commands.InitCommand._INIT_TEMPLATE_YAML
        )
    )

    assert len(rock_project.summary) < 80
    assert len(rock_project.description.split()) < 100

    assert lifecycle_init_mock.mock_calls == [
        call(cli.commands.InitCommand._INIT_TEMPLATE_YAML)  # pylint: disable=W0212
    ]
    assert mock_ended_ok.mock_calls == [call()]


def test_run_arg_parse_error(capsys, mocker):
    """Catch ArgumentParsingError and exit cleanly."""
    mocker.patch.object(sys, "argv", ["rockcraft", "invalid-command"])
    mock_emit = mocker.patch("rockcraft.cli.emit")
    mock_exit = mocker.patch("rockcraft.cli.sys.exit")

    cli.run()

    mock_emit.ended_ok.assert_called_once()
    mock_exit.assert_called_once()

    out, err = capsys.readouterr()
    assert not out
    assert "Error: no such command 'invalid-command'" in err


def test_run_arg_provider_help_exception(capsys, mocker):
    """Catch ProviderHelpException and exit cleanly."""
    mocker.patch(
        "craft_cli.Dispatcher.pre_parse_args",
        side_effect=ProvideHelpException("test help message"),
    )
    mock_emit = mocker.patch("rockcraft.cli.emit")

    cli.run()

    mock_emit.ended_ok.assert_called_once()

    out, err = capsys.readouterr()
    assert not out
    assert err == "test help message\n"


@pytest.mark.parametrize(
    "input_error, output_error",
    [
        (RockcraftError("test error"), CraftError("test error")),
        (ProviderError("test error"), CraftError("craft-providers error: test error")),
        (
            Exception("test error"),
            CraftError("rockcraft internal error: Exception('test error')"),
        ),
    ],
)
def test_run_with_error(mocker, input_error, output_error):
    """Application errors should be caught for a clean exit."""
    mocker.patch("craft_cli.Dispatcher.run", side_effect=input_error)
    mocker.patch.object(sys, "argv", ["rockcraft", "pack"])
    mock_emit = mocker.patch("rockcraft.cli.emit")
    mock_exit = mocker.patch("rockcraft.cli.sys.exit")

    cli.run()

    mock_exit.assert_called_once()
    mock_emit.error.assert_called_once_with(output_error)
