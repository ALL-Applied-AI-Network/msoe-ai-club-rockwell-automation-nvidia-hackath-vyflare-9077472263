"""Numerical reference-color guard for recorded pattern discovery.

Withholding an unstable color never removes timing evidence or candidate IDs.
The historical reviewed-trial helper/schema remain unchanged.
"""
from copy import deepcopy
import math
from .reviewed_trial import compare_color

def rejection_reasons(profile,rules):
    raw=profile.get('raw_rgb');reasons=[]
    if not isinstance(raw,dict):return ['MISSING_REFERENCE_COLOR']
    rgb=raw.get('nominal')
    if not isinstance(rgb,list) or len(rgb)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=255 for x in rgb):
        reasons.append('INVALID_REFERENCE_RGB')
    for metric,limit,code in [('temporal_distance','temporal_distance_limit','REFERENCE_TEMPORAL_LIMIT_EXCEEDED'),
                              ('region_distance','placement_distance_limit','REFERENCE_SPATIAL_LIMIT_EXCEEDED')]:
        value=raw.get(metric)
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:reasons.append('MISSING_OR_INVALID_REFERENCE_'+metric.upper())
        elif value>rules[limit]:reasons.append(code)
    return reasons


def qualified_color(observation,candidate_ids,profiles,rules):
    qualified=[];excluded=[]
    for source in profiles:
        profile=deepcopy(source);reasons=rejection_reasons(profile,rules)
        if reasons:
            excluded.append({'profile_id':profile['vial_uid'],'recipe_id':profile['recipe_id'],'reasons':reasons})
            # Keep profile timing/identity present. Only its color is withheld.
            profile['raw_rgb']=None
        qualified.append(profile)
    result=compare_color(observation,candidate_ids,qualified,rules)
    result['reference_color_qualification']={'excluded_profiles':excluded,
        'missing_qualified_color_recipe_ids':[rid for rid in candidate_ids if not any(p['recipe_id']==rid and p['raw_rgb'] is not None for p in qualified)],
        'qualified_profile_count':sum(p['raw_rgb'] is not None for p in qualified),
        'scope':'EXISTING_NUMERICAL_STABILITY_LIMITS_ONLY_NOT_CAPTURE_OR_PHASE_VALIDATION'}
    return result

