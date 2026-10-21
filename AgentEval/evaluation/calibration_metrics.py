"""Every fraction retains its real denominator and drill-down identities."""
from collections import Counter

def fraction(numerator_ids, denominator_ids):
    return {'numerator':len(numerator_ids), 'denominator':len(denominator_ids),
            'value':len(numerator_ids)/len(denominator_ids) if denominator_ids else None,
            'numerator_ids':numerator_ids, 'denominator_ids':denominator_ids}

def adoption_restrictions(comparison):
    """A reusable profile needs decisions for the entire frozen validation scope."""
    reasons=[]
    if not comparison.get('comparable'):
        reasons.append('COMPARISON_NOT_COMPARABLE')
    for side in ('metrics_before','metrics_after'):
        metrics=comparison.get(side,{})
        reconciliation=metrics.get('reconciliation',{})
        expected=reconciliation.get('expected',0)
        if not expected or reconciliation.get('balanced') is not True:
            reasons.append(side.upper()+'_RESULT_IDS_INCOMPLETE')
        for key in ('coverage','paired_coverage'):
            value=metrics.get(key,{})
            if not expected or value.get('denominator')!=expected or value.get('numerator')!=expected:
                reasons.append(side.upper()+'_'+key.upper()+'_INCOMPLETE')
    return reasons

def compute_metrics(samples, results, references, repetitions):
    key_counts=Counter((r.sample_id,r.repetition) for r in results)
    by_key={(r.sample_id,r.repetition):r for r in results if key_counts[(r.sample_id,r.repetition)]==1}
    ids=[];binary=[];paired=[];agree=[];hfail=[];hpass=[];falsepass=[];falsefail=[];critical=[];miss=[]
    critical_unknown=[];human_binary=[];unavailable_fail=[];unavailable_pass=[];health=Counter();matrix={h:{m:[] for m in ('PASS','FAIL')} for h in ('PASS','FAIL')}
    rows=[]
    resolution={'human':Counter(),'machine':Counter()};faithfulness={'human':Counter(),'machine':Counter()}
    failures={'human':Counter(),'machine':Counter()};answer_errors={'human':Counter(),'machine':Counter()}
    for sample in samples:
        ref=references.get(sample.sample_id,{})
        human=ref.get('judgment');hv=human.get('verdict') if human else None
        for repetition in range(1,repetitions+1):
            key=f'{sample.sample_id}:{repetition}';ids.append(key)
            result=by_key.get((sample.sample_id,repetition));machine=result.judgment if result and result.status=='SUCCESS' else None
            mv=machine.verdict if machine else None
            status=result.status if result else 'DUPLICATE_RESULT' if key_counts[(sample.sample_id,repetition)]>1 else 'NOT_RUN';health[status]+=1
            for side,value in (('human',human),('machine',machine.model_dump() if machine else None)):
                resolution[side][value['task_resolved'] if value else 'UNAVAILABLE']+=1
                faithfulness[side][value['faithful_to_available'] if value else 'UNAVAILABLE']+=1
                if value:
                    failures[side].update(set(value['task_failure_reasons']))
                    answer_errors[side].update(set(value['error_tags']))
            if mv=='PENDING': health['EVIDENCE_INSUFFICIENT']+=1
            if hv not in ('PASS','FAIL'): health['HUMAN_UNRESOLVED']+=1
            if ref.get('state')=='DISAGREEMENT': health['HUMAN_DISAGREEMENT']+=1
            if mv in ('PASS','FAIL'): binary.append(key)
            if hv in ('PASS','FAIL'): human_binary.append(key)
            if hv=='FAIL':
                hfail.append(key)
                if mv not in ('PASS','FAIL'): unavailable_fail.append(key)
            if hv=='PASS':
                hpass.append(key)
                if mv not in ('PASS','FAIL'): unavailable_pass.append(key)
            relation='UNPAIRED'
            if hv in ('PASS','FAIL') and mv in ('PASS','FAIL'):
                paired.append(key);matrix[hv][mv].append(key)
                if hv==mv: agree.append(key);relation='AGREE'
                elif hv=='FAIL': falsepass.append(key);relation='FALSE_PASS'
                else: falsefail.append(key);relation='FALSE_FAIL'
            if human and human.get('critical_errors'):
                critical.append(key)
                if machine is None: critical_unknown.append(key)
                elif set(human['critical_errors'])-set(machine.critical_errors): miss.append(key)
            rows.append({'key':key,'sample_id':sample.sample_id,'repetition':repetition,'human':hv,'machine':mv,
                'execution_status':status,'reference_state':ref.get('state','MISSING'),'relation':relation,
                'error':result.error if result else None,
                'human_critical_errors':human.get('critical_errors',[]) if human else [],
                'machine_critical_errors':machine.critical_errors if machine else [],
                'scenario':sample.scenario,'diagnostic':sample.diagnostic,'origin':sample.origin})
    usage_rows=[r.usage for r in results if r.usage is not None]
    expected={(s.sample_id,i) for s in samples for i in range(1,repetitions+1)}
    unexpected=sum(count for key,count in key_counts.items() if key not in expected)
    duplicate=sum(count-1 for key,count in key_counts.items() if key in expected and count>1)
    missing=len(expected-set(key_counts))
    repeated=[s.sample_id for s in samples] if repetitions>1 else []
    complete_repeats=[];stable=[]
    for sid in repeated:
        values=[by_key.get((sid,i)) for i in range(1,repetitions+1)]
        if all(r and r.status=='SUCCESS' and r.judgment and r.judgment.verdict in ('PASS','FAIL') for r in values):
            complete_repeats.append(sid)
            if len({r.judgment.verdict for r in values})==1: stable.append(sid)
    metrics={'expected_judgments':len(ids),'sample_count':len(samples),'repetitions':repetitions,
        'agreement':fraction(agree,paired),'false_pass':fraction(falsepass,hfail),'false_fail':fraction(falsefail,hpass),
        'critical_miss':fraction(miss,critical),'critical_unavailable':fraction(critical_unknown,critical),
        'coverage':fraction(binary,ids),'paired_coverage':fraction(paired,ids),'health':dict(health),
        'human_reference_coverage':fraction(human_binary,ids),
        'unavailable_on_human_fail':fraction(unavailable_fail,hfail),'unavailable_on_human_pass':fraction(unavailable_pass,hpass),
        'repeat_stability':fraction(stable,repeated),'repeat_complete':fraction(complete_repeats,repeated),
        'reconciliation':{'expected':len(expected),'received':len(results),'missing':missing,'duplicates':duplicate,
                          'unexpected':unexpected,'balanced':not (missing or duplicate or unexpected)},
        'machine_decisions':{'pass':sum(r['machine']=='PASS' for r in rows),'fail':sum(r['machine']=='FAIL' for r in rows),
                             'pending':sum(r['machine']=='PENDING' for r in rows),'unavailable':sum(r['machine'] is None for r in rows)},
        'matrix':{h:{m:{'count':len(v),'ids':v} for m,v in cols.items()} for h,cols in matrix.items()},'rows':rows,
        'task_resolution':{k:dict(v) for k,v in resolution.items()},
        'faithfulness':{k:dict(v) for k,v in faithfulness.items()},
        'task_failure_reasons':{k:dict(v) for k,v in failures.items()},
        'answer_error_tags':{k:dict(v) for k,v in answer_errors.items()},
        'cost':{'request_count':sum(r.request_count for r in results),'latency_ms':sum(r.latency_ms for r in results),
                'usage_available_judgments':len(usage_rows),'usage_unknown_judgments':len(ids)-len(usage_rows),
                'usage':{k:sum(u.get(k,0) for u in usage_rows if isinstance(u.get(k),(int,float)))
                         for k in ('input_tokens','output_tokens')} if usage_rows else None,'currency_cost':None},
        'rate_note':'错误放行/拒绝分母包括有人工二元参照但机器弃判或执行失败的项；未评价项单列，不视为正确。重复次数为评分事件分母。'}
    return metrics

def metrics_with_slices(samples, results, references, repetitions):
    all_metrics=compute_metrics(samples,results,references,repetitions)
    def subset(selected):
        ids={s.sample_id for s in selected}
        return compute_metrics(selected,[r for r in results if r.sample_id in ids],references,repetitions)
    all_metrics['by_scenario']={scenario:subset([s for s in samples if s.scenario==scenario]) for scenario in sorted({s.scenario for s in samples})}
    all_metrics['by_distribution']={'diagnostic':subset([s for s in samples if s.diagnostic]),
        'non_diagnostic':subset([s for s in samples if not s.diagnostic]),
        'actual_natural':subset([s for s in samples if not s.diagnostic and s.origin=='ACTUAL'])}
    return all_metrics
