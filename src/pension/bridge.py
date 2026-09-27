"""M7 basis bridge (SPEC §9 M7): IAS 19 DBO -> Funding Standard liability by sequential full revaluations.

Bridge effects are sequential rather than unique standalone decompositions.
"""
from pension import cashflows, funding_standard as fs, ias19

STEPS = [
    ("ias19", "IAS 19 DBO", "all"),
    ("leaver_basis", "Leaver basis: no salary growth, no withdrawal", "actives"),
    ("s34_mortality", "Section 34 mortality and annuity loading", "non-pensioners"),
    ("s34_increases", "Revaluation and increases at 1.5%", "non-pensioners"),
    ("s34_discount", "6% / 4.25% discount x MVA", "non-pensioners"),
    ("annuity_cost", "Annuity purchase cost", "pensioners"),
    ("expenses", "Wind-up expenses", "all"),
]


def run(members, valuation_date):
    pens = (members.status == "P").to_numpy()
    non_p, p = members[~pens], members[pens]
    b_ias = ias19.basis(valuation_date)
    curve = ias19.curve(valuation_date)
    s34 = fs.s34_basis(valuation_date)

    def pv_ias19_curve(group, b):
        return cashflows.pv(cashflows.project_cashflows(group, b), curve).sum()

    pensioners_ias19 = pv_ias19_curve(p, b_ias)
    leaver = b_ias.with_(actives_as_leavers=True)
    mortality = leaver.with_(mortality_pre=s34.mortality_pre, mortality_post=s34.mortality_post,
                             annuity_loading=s34.annuity_loading)
    increases = mortality.with_(revaluation=s34.revaluation, pension_increase=s34.pension_increase)
    tv, _ = fs.transfer_values(non_p, increases, fs.mva_npa_at(valuation_date))
    annuities, _ = fs.annuity_costs(p, fs.annuity_basis(valuation_date), fs.annuity_curve(valuation_date))

    levels = {}
    levels["ias19"] = pv_ias19_curve(non_p, b_ias) + pensioners_ias19
    levels["leaver_basis"] = pv_ias19_curve(non_p, leaver) + pensioners_ias19
    levels["s34_mortality"] = pv_ias19_curve(non_p, mortality) + pensioners_ias19
    levels["s34_increases"] = pv_ias19_curve(non_p, increases) + pensioners_ias19
    levels["s34_discount"] = tv.sum() + pensioners_ias19
    levels["annuity_cost"] = tv.sum() + annuities.sum()
    levels["expenses"] = levels["annuity_cost"] + fs.wind_up_expenses(levels["annuity_cost"])

    keys = [k for k, _, _ in STEPS]
    steps = []
    for i, (key, label, who) in enumerate(STEPS):
        effect = levels[key] if i == 0 else levels[key] - levels[keys[i - 1]]
        steps.append({"step": i, "key": key, "change": label, "members": who, "effect": effect, "level": levels[key]})
    return steps
