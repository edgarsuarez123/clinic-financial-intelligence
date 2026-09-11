"""Small, backtested monthly forecasts. Decimal arithmetic; no invented missing data."""
from datetime import date
from decimal import Decimal
from ..analytics.calculations import exact
from .calculations import anniversary

ZERO=Decimal('0')

def estimate(values,method,h):
    n=len(values)
    if method=='last_month': return values[-1]
    if method=='trailing_mean': return sum(values[-6:],ZERO)/Decimal(min(n,6))
    if method=='seasonal_naive': return values[n-12+(h-1)%12]
    # Damped extrapolation is not silently substituted: trend is ordinary least squares.
    xmean=Decimal(n-1)/2; ymean=sum(values,ZERO)/n
    slope=sum(((Decimal(i)-xmean)*(v-ymean) for i,v in enumerate(values)),ZERO)/sum(((Decimal(i)-xmean)**2 for i in range(n)),ZERO)
    return ymean+slope*(Decimal(n-1+h)-xmean)

def percentile(values,p):
    ordered=sorted(values);position=Decimal(len(values)-1)*p
    low=int(position);fraction=position-low
    return ordered[low] if low==len(values)-1 else ordered[low]+fraction*(ordered[low+1]-ordered[low])

@exact
def forecast_months(rows,horizon=6,as_of=None):
    if type(horizon) is not int or not 1<=horizon<=12: raise ValueError('Forecast horizon must be 1–12 months.')
    if len(rows)<24: raise ValueError('History-based forecasts require at least 24 consecutive complete months. Use assumption-based scenarios for shorter histories.')
    periods=[date.fromisoformat(str(r['period'])[:10]) for r in rows]
    if any(d.day!=1 or (i and d!=anniversary(periods[i-1],1)) for i,d in enumerate(periods)): raise ValueError('Forecast history must contain consecutive calendar months; missing months are not zero.')
    if as_of and anniversary(periods[-1],1)>as_of: raise ValueError('Exclude the current incomplete month from forecast history.')
    values=[Decimal(str(r['revenue'])) for r in rows]
    if any(not v.is_finite() or v<0 for v in values) or sum(values,ZERO)==ZERO: raise ValueError('Revenue history must be nonnegative with recorded activity.')
    n=len(values);split=max(12,n//2)
    # Select on an earlier prefix. Hold out later origins for calibration/reporting.
    methods=['last_month','trailing_mean','linear_trend']
    if split>=32: methods.append('seasonal_naive')
    first_origin=24 if 'seasonal_naive' in methods else 12
    scores={m:sum((abs(values[i]-max(ZERO,estimate(values[:i],m,1))) for i in range(first_origin,split)),ZERO)/Decimal(split-first_origin) for m in methods if split>first_origin}
    if not scores: scores={'last_month':ZERO}
    selected=min(scores,key=scores.get)
    errors={h:[values[i+h-1]-max(ZERO,estimate(values[:i],selected,h)) for i in range(split,n-h+1)] for h in range(1,horizon+1)}
    if any(len(e)<8 for e in errors.values()): raise ValueError('Not enough held-out months for this horizon. Select a shorter forecast or import more history (at least eight validation errors per horizon).')
    naive_error=sum((abs(values[i]-values[i-1]) for i in range(split,n)),ZERO)/Decimal(n-split)
    mae=sum((abs(e) for e in errors[1]),ZERO)/len(errors[1])
    fallback=selected!='last_month' and mae>=naive_error
    if fallback:
        # Conservative benchmark fallback. Report that calibration was reused to reject the candidate.
        selected='last_month'
        errors={h:[values[i+h-1]-values[i-1] for i in range(split,n-h+1)] for h in range(1,horizon+1)}
        mae=naive_error
    periods_out=[]
    for h in range(1,horizon+1):
        center=max(ZERO,estimate(values,selected,h))
        lower=max(ZERO,center+min(ZERO,percentile(errors[h],Decimal('.1'))))
        upper=max(center,center+percentile(errors[h],Decimal('.9')))
        periods_out.append({'period':anniversary(periods[-1],h).isoformat(),'revenue':center.quantize(Decimal('.01')),
            'lower_80':lower.quantize(Decimal('.01')),'upper_80':upper.quantize(Decimal('.01')),'validation_windows':len(errors[h])})
    return {'method':selected,'history_months':n,'validation_mae':mae.quantize(Decimal('.01')),
        'benchmark_fallback':fallback,
        'benchmark_mae':naive_error.quantize(Decimal('.01')),'periods':periods_out,
        'basis':'Monthly collected revenue; rolling-origin validation. Estimated ranges use held-out error percentiles, not guaranteed probabilities. Trend is not causal; future payer mix, policy changes and new hires are not inferred.'}
