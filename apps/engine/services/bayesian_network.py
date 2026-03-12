from pgmpy.models import DiscreteBayesianNetwork
from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination

def build_bayesian_network():
    model = DiscreteBayesianNetwork([('Risk_Profile_Score', 'Asset_Suitability'), ('Expected_Return', 'Asset_Suitability'), ('Volatility', 'Asset_Suitability')])
    cpd_risk = TabularCPD(variable='Risk_Profile_Score', variable_card=5, values=[[0.2], [0.2], [0.2], [0.2], [0.2]])
    cpd_return = TabularCPD(variable='Expected_Return', variable_card=3, values=[[0.33], [0.33], [0.34]])
    cpd_volatility = TabularCPD(variable='Volatility', variable_card=3, values=[[0.33], [0.33], [0.34]])
    suitability_high_probs = build_heuristic_cpt_array()
    suitability_low_probs = [1 - p for p in suitability_high_probs]
    cpd_suitability = TabularCPD(
        variable='Asset_Suitability', variable_card=2, 
        values=[suitability_low_probs, suitability_high_probs],
        evidence=['Risk_Profile_Score', 'Expected_Return', 'Volatility'],
        evidence_card=[5, 3, 3]
    )
    model.add_cpds(cpd_risk, cpd_return, cpd_volatility, cpd_suitability)
    assert model.check_model()
    return VariableElimination(model)

def build_heuristic_cpt_array():
    probs = []
    for risk in range(5):        
        for ret in range(3):     
            for vol in range(3): 
                score = 0.5 
                if risk == 0:
                    if vol == 2: score = 0.05
                    elif vol == 0: score = 0.90
                elif risk == 4:
                    if vol == 2 and ret == 2: score = 0.95
                    elif vol == 0: score = 0.20
                elif risk == 2:
                    if vol == 1 and ret == 1: score = 0.80
                    if vol == 0 or vol == 2: score = 0.40
                else:
                    if vol >= risk: score = max(0.1, 0.5 - (vol - risk) * 0.2)
                    else: score = min(0.9, 0.5 + (risk - vol) * 0.2)
                if ret == 2 and risk >= 2: score = min(0.99, score + 0.15)
                if ret == 0 and risk <= 1: score = min(0.99, score + 0.10)
                probs.append(score)
    return probs
