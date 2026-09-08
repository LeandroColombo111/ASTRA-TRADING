"""Every shipped config must route to its own strategy family.

This suite exists because of a real defect: `service.py` gained a strategy
selector while `cli.py` kept importing the v1 parameter class directly, so
`astra replay` raised on the active v4 config and would silently have replayed
a different strategy had the windows happened to validate. A config that the
CLI cannot load is a config nobody can verify.
"""
import json
from pathlib import Path

import pytest

from astra.engine import Risk
from astra.service import strategy_for, backtest_for

CONFIGS = sorted(Path('configs').glob('selected*.json'))


def test_configs_exist():
    assert CONFIGS, 'No selected*.json configs found'


@pytest.mark.parametrize('path', CONFIGS, ids=lambda p: p.name)
def test_config_loads_through_its_declared_strategy(path):
    cfg = json.loads(path.read_text())
    name = cfg.get('strategy')
    params_class, features_fn = strategy_for(name)
    backtest = backtest_for(name)
    # The parameter class must accept the stored parameters verbatim. A window
    # outside the family's validated range fails here rather than at runtime.
    params = params_class(**cfg['params'])
    Risk(**cfg['risk'])
    assert callable(features_fn) and callable(backtest)
    # Parameters and features must come from the same module. The backtest may
    # live elsewhere: the v1 family keeps its signal in directional_strategy and
    # its engine in engine, while v4 keeps both in v4_hourly. What matters is
    # that the resolver hands back a matched set, verified below.
    assert params_class.__module__ == features_fn.__module__, (
        'Parameters and features must come from one family')
    expected = {'v4_hourly': 'astra.v4_hourly'}.get(name, 'astra.engine')
    assert backtest.__module__ == expected, (
        'Config %s routes to backtest %s, expected %s' % (path.name, backtest.__module__, expected))


@pytest.mark.parametrize('path', CONFIGS, ids=lambda p: p.name)
def test_no_config_claims_live_approval(path):
    cfg = json.loads(path.read_text())
    assert cfg.get('approved_for_live') is False, 'A shipped config must not claim live approval'


def test_active_config_is_not_the_deprecated_family():
    cfg = json.loads(Path('configs/selected.json').read_text())
    assert not cfg.get('deprecated'), 'The default config must not be a deprecated run'
    assert cfg.get('strategy') == 'v4_hourly', (
        'The default config should serve the current research family; update this '
        'test deliberately when the served strategy changes')


def test_unknown_strategy_is_refused_not_defaulted():
    for resolver in (strategy_for, backtest_for):
        with pytest.raises(ValueError):
            resolver('a-family-that-does-not-exist')


def test_v1_still_resolves_for_audit_replay():
    params_class, features_fn = strategy_for('v1')
    backtest = backtest_for('v1')
    assert params_class.__module__.endswith('directional_strategy')
    assert callable(features_fn) and callable(backtest)
