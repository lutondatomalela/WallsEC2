"""Conservative elastic screening for mechanically induced cracking.
Not a normative crack-width model. 0.7 fctm is the lower characteristic
strength (EC2 Table 3.1); no assumption of no earlier cracks is made.
A zero is conditional on a complete history, absence of imposed strain,
local effects, and strength at load age. It never overwrites wk.
"""
from dataclasses import dataclass
import math
import numpy as np

@dataclass(frozen=True)
class HistoryScreen:
    status: str
    ratio: float
    wk_conditional_mm: float


def classify_history(stresses,fctm,*,complete):
    v=np.asarray(stresses,float)
    if not math.isfinite(fctm) or fctm<=0:raise ValueError('fctm inválido')
    if not complete or v.size==0 or not np.isfinite(v).all() or np.any(v<0):
        return HistoryScreen('Histórico mecânico importado incompleto',math.nan,math.nan)
    ratio=float(v.max()/(.7*fctm))
    if ratio<=1+1e-9:
        return HistoryScreen('Sem excedência de fctk,0.05; wk=0 apenas se história/coacção/idade confirmadas',ratio,0.)
    return HistoryScreen('Excede fctk,0.05; cálculo de abertura acoplada necessário',ratio,math.nan)
