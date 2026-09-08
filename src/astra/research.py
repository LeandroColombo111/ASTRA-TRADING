"""Brief v2 stage gates. No optimizer can run before universe/signal admission.

Original bootstrap and DSR functions are reused unchanged. Original directional
research remains in legacy_research.py for historical audit only.
"""
from pathlib import Path
import json
import math
from .legacy_research import monte_carlo,deflated_sharpe,dump

class ResearchGateError(RuntimeError):
    pass


def cost_gate(gross_before_costs,total_costs):
    if not math.isfinite(gross_before_costs) or not math.isfinite(total_costs):
        return {'passed':False,'ratio':None,'reason':'nonfinite_accounting'}
    if total_costs<0:
        return {'passed':False,'ratio':None,'reason':'negative_costs'}
    if gross_before_costs<=0:
        return {'passed':False,'ratio':None,'reason':'nonpositive_gross'}
    ratio=total_costs/gross_before_costs
    return {'passed':ratio<=.30,'ratio':ratio,'reason':'pass' if ratio<=.30 else 'costs_exceed_30pct_gross'}


def require_precheck(output='reports/v2-sleeve1',attempts=60):
    """Fail before allocating any optimization attempt; never revive an archive."""
    if not 1<=attempts<=60:raise ResearchGateError('Hard v2 search budget: 1..60 configurations')
    out=Path(output)
    protocol=json.loads((out/'protocol.json').read_text())
    if protocol['parameter_count']>5:raise ResearchGateError('At most five free parameters')
    if (out/'run.closed').exists():raise ResearchGateError('Run archived; no new search on the same data')
    universe=json.loads((out/'universe_gate.json').read_text())
    if universe['status']!='UNIVERSE_GATE_PASSED':raise ResearchGateError('Universe below 25: precheck and optimization prohibited; 0 attempts used')
    precheck_path=out/'signal_precheck.json'
    if not precheck_path.exists():raise ResearchGateError('Signal precheck not measured; optimization prohibited')
    precheck=json.loads(precheck_path.read_text())
    if not precheck.get('historical_spread_costs_verified'):raise ResearchGateError('Historical per-symbol spread coverage is mandatory')
    if not precheck.get('funding_verified'):raise ResearchGateError('Actual OKX funding coverage is mandatory')
    net=precheck.get('primary_daily_net_sharpe')
    if net is None or not math.isfinite(net) or net<=.3:raise ResearchGateError('Raw net Sharpe must exceed 0.3; family rejected before optimization')
    return protocol


def status(output='reports/v2-sleeve1'):
    out=Path(output)
    if (out/'report.json').exists():return json.loads((out/'report.json').read_text())
    if (out/'universe_gate.json').exists():return json.loads((out/'universe_gate.json').read_text())
    return {'status':'NOT_MEASURED','optimization_attempts':0,'approved_for_live':False}
