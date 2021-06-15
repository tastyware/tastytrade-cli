from src.quant import models as sc


def test_quant():
    # this is the simple test from the cookbook
    # for european with bsm
    m = sc.Model(price_underlying=100.0, price_strike=100, volatility=0.2,
                 rate_risk_free=0.01, date_expiration='2014-06-07',
                 date_evaluation='2014-03-07', option_type='call',
                 exercise_type='european',)
    hyp = 4.155543462156206
    msg = 'Known model output should match calculated value.'
    assert abs(m.option.NPV() - hyp) / hyp < 0.01, msg

    # for american with binomial
    m = sc.Model(price_underlying=100.0, price_strike=100, volatility=0.2,
                 rate_risk_free=0.01, date_expiration='2014-06-07',
                 date_evaluation='2014-03-07', option_type='call',
                 exercise_type='american',)
    hyp = 4.155543462156206
    msg = 'Known model output should match calculated value.'
    assert abs(m.option.NPV() - hyp) / hyp < 0.01, msg
