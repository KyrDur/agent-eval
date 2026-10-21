// Only route shapes and fixed enums are inspected. Payload contents never enter analytics.
export function operationFor(path, body, meta = {}) {
  const route=path.split('?')[0]
  const exact={
    '/provider-sessions':'setup.save','/knowledge-datasets':'knowledge.save',
    '/chat-turns':'chat.send','/ai/knowledge':'knowledge.generate','/ai/tests':'tests.generate',
    '/ai/trace':'trace.analyze','/retrieval-evalsets':'tests.save','/evalsets':'tests.save',
    '/retrieval-runs':body?.run_type==='RETEST'?'run.retest':'run.baseline',
    '/retrieval-run-tasks':body?.run_type==='RETEST'?'run.retest':'run.baseline',
    '/runs':body?.run_type==='RETEST'?'run.retest':'run.baseline',
    '/retrieval-comparisons':'comparison.create','/comparisons':'comparison.create',
    '/retrieval-changes':'change.propose','/decisions':'change.diagnose','/changes':'change.record',
    '/retrieval-rewrite-preview':'change.preview','/retrieval-repeats':'run.repeat',
    '/career/evidence':meta.confirmed?'career.confirm':'career.evidence',
    '/career/narrative/preview':'career.preview','/career/materials':'career.generate',
    '/career/materials/v2':'career.generate','/interview-attempts':'interview.save',
  }
  let action=body===undefined?null:exact[route]
  const patterns=[
    [/^\/provider-sessions\/[^/]+\/test$/,'setup.test'],
    [/^\/provider-sessions\/[^/]+\/test-tools$/,'setup.tools'],
    [/^\/provider-sessions\/[^/]+\/judge$/,'judge.bind'],
    [/^\/knowledge-datasets\/[^/]+\/index$/,'knowledge.index'],
    [/^\/chat-turns\/[^/]+\/test-draft$/,'chat.draft'],
    [/^\/(retrieval-runs|runs)\/[^/]+\/reviews$/,'review.save'],
    [/^\/decisions\/[^/]+\/confirm$/,'change.confirm'],
    [/^\/(retrieval-changes|changes)\/[^/]+\/apply$/,'change.apply'],
    [/^\/changes\/[^/]+\/rollback$/,'change.rollback'],
    [/^\/retrieval-comparisons\/[^/]+\/conclusions$/,'conclusion.save'],
    [/^\/career\/materials\/[^/]+\/edit$/,'career.edit'],
    [/^\/career\/materials\/[^/]+\/regenerate-section$/,'career.regenerate'],
  ]
  if(body!==undefined && !action)action=patterns.find(([re])=>re.test(route))?.[1]
  if(body===undefined && /^\/career\/materials\/[^/]+\/export$/.test(route))action='career.fetch'
  if(!action)return null
  if(meta.regenerate && action==='knowledge.generate')action='knowledge.regenerate'
  if(meta.role==='judge' && action==='setup.save')action='judge.save'
  if(meta.role==='judge' && action==='setup.test')action='judge.connect'
  if(meta.restore && action==='judge.bind')action='judge.restore'
  const material=meta.material || ({case_study:'project',resume_ai:'resume',resume_general:'resume',interview:'interview',defense:'interview'})[body?.group]
  return {action,role:meta.role || (action.startsWith('setup.')?'main':['knowledge.generate','knowledge.regenerate','tests.generate','trace.analyze'].includes(action)?'auxiliary':'unknown'),material:material || (action==='career.generate'?'all':action==='interview.save'?'interview':'unknown'),context:meta.context||'unknown'}
}
