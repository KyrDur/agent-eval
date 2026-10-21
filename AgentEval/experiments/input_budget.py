"""Conservative full-request bounds, before any network acquisition."""
import json
from .providers import ProviderFailure

def preflight(request, window=32768):
    # UTF-8 bytes are a conservative upper bound for supported byte-tokenizers.
    # Unknown providers use an explicit configured limit, not guessed model specs.
    try:size=len(json.dumps(request,ensure_ascii=False,separators=(',',':'),default=lambda value:value.model_dump(mode='json')).encode('utf-8'))
    except (ValueError,TypeError,AttributeError):raise ProviderFailure('INPUT_SCHEMA_INVALID') from None
    reserve=request.get('max_tokens',4096)
    result={'method':'UTF8_BYTE_UPPER_BOUND','input_upper_bound':size+256,
        'output_reserved':reserve,'configured_window':window,'model_limit_verified':False}
    result['allowed']=size+256+reserve<=window
    if not result['allowed']:raise ProviderFailure('INPUT_BUDGET_EXCEEDED')
    return result
