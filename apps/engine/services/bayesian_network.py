from pgmpy.models import DiscreteBayesianNetwork
from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination


def build_bayesian_network():
    model = DiscreteBayesianNetwork([
        ('Risk_Profile_Score', 'Asset_Suitability'),
        ('Expected_Return', 'Asset_Suitability'),
        ('Volatility', 'Asset_Suitability'),
    ])

    cpd_risk = TabularCPD(
        variable='Risk_Profile_Score', variable_card=5,
        values=[[0.2], [0.2], [0.2], [0.2], [0.2]],
    )
    cpd_return = TabularCPD(
        variable='Expected_Return', variable_card=3,
        values=[[0.33], [0.33], [0.34]],
    )
    cpd_volatility = TabularCPD(
        variable='Volatility', variable_card=3,
        values=[[0.33], [0.33], [0.34]],
    )

    suitability_high_probs = _build_cpt()
    suitability_low_probs = [1 - p for p in suitability_high_probs]

    cpd_suitability = TabularCPD(
        variable='Asset_Suitability', variable_card=2,
        values=[suitability_low_probs, suitability_high_probs],
        evidence=['Risk_Profile_Score', 'Expected_Return', 'Volatility'],
        evidence_card=[5, 3, 3],
    )

    model.add_cpds(cpd_risk, cpd_return, cpd_volatility, cpd_suitability)
    assert model.check_model()
    return VariableElimination(model)


# ── Conditional Probability Table ────────────────────────────
#
# Explicit P(Suitability=high | risk, return_tier, volatility_tier).
# Each risk level has a distinct 3x3 return-vs-volatility matrix
# so that different risk profiles produce meaningfully different
# portfolio compositions.
#
# Layout per risk level:
#              vol=low   vol=mod   vol=high
# ret=low      [a]       [b]       [c]
# ret=mod      [d]       [e]       [f]
# ret=high     [g]       [h]       [i]

_CPT_MATRIX = {
    # Risk 0 – Very Conservative: love low-vol, avoid any high-vol
    0: [
        0.85, 0.40, 0.05,   # ret=low
        0.80, 0.35, 0.05,   # ret=mod
        0.70, 0.30, 0.03,   # ret=high
    ],
    # Risk 1 – Conservative: prefer low-vol, tolerate moderate
    1: [
        0.75, 0.55, 0.10,   # ret=low
        0.80, 0.60, 0.15,   # ret=mod
        0.70, 0.55, 0.12,   # ret=high
    ],
    # Risk 2 – Moderate: balanced, moderate-everything sweet spot
    2: [
        0.45, 0.55, 0.20,   # ret=low
        0.55, 0.80, 0.35,   # ret=mod
        0.50, 0.75, 0.40,   # ret=high
    ],
    # Risk 3 – Aggressive: want high return, tolerate high vol
    3: [
        0.15, 0.30, 0.40,   # ret=low
        0.25, 0.55, 0.65,   # ret=mod
        0.40, 0.70, 0.90,   # ret=high
    ],
    # Risk 4 – Very Aggressive: maximise return, embrace vol
    4: [
        0.05, 0.15, 0.30,   # ret=low
        0.10, 0.40, 0.60,   # ret=mod
        0.30, 0.65, 0.95,   # ret=high
    ],
}


def _build_cpt():
    """Return flat list in pgmpy's expected order: risk → return → volatility."""
    probs = []
    for risk in range(5):
        matrix = _CPT_MATRIX[risk]
        for ret in range(3):
            for vol in range(3):
                probs.append(matrix[ret * 3 + vol])
    return probs
