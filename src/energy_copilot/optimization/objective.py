"""C2/C3 single-unit objectives. Energy and cost remain separately reported."""
import pyomo.environ as pyo


def set_objective(model,inp):
    model.objective.deactivate()
    if inp.objective_mode=='energy':expression=sum(model.total_energy[t] for t in model.T)
    elif inp.objective_mode=='cost':expression=sum(model.total_energy[t]*inp.tariff_calendar[t].Rs_per_kWh for t in model.T)
    else:raise ValueError('Expected energy or cost objective')
    model.primary_objective=pyo.Objective(expr=expression,sense=pyo.minimize)
