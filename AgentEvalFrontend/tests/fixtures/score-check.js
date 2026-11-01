// Saved records for software checks only; no real users, credentials or model calls.
export function savedScoreView(){
 const rubric={name:'客服回答评分细则 · 保存版本一',applicable_scope:'店铺知识问答',dimensions:{
  faithfulness:{label:'有据可依',anchors:{0:'编造资料没有的承诺',1:'部分有据可依',2:'每项结论都有依据'},applicability:'需要使用资料的回答'},
  conditions:{label:'条件完整',anchors:{0:'遗漏决定性条件',1:'遗漏次要条件',2:'条件完整'}},
 },critical_errors:{unsupported_promise:'不得凭空承诺包邮'},rules:{minimum_scores:{faithfulness:2,conditions:2},na_allowed:['actionability'],insufficient_policy:'ABSTAIN',critical_error_policy:'FAIL'}}
 const queries=['订单实付 89 元，寄上海包邮吗？','SVALKA 玻璃杯容量是多少？']
 const answers=['可以，您的订单可以包邮。','这款玻璃杯容量为 300 毫升。']
 const refs=['订单实付满 99 元、寄往中国大陆普通地区才包邮；上海适用。','SVALKA 玻璃杯容量为 300 毫升。']
 const reasons=['实付 89 元未满 99 元，回答却承诺包邮。','回答准确给出了资料中的容量。']
 const specs=queries.map((query,i)=>({case_id:`case-${i+1}`,query,partition:'DEBUG',reference_complete:true,expected_answer:i?'容量为 300 毫升。':'89 元未达到 99 元包邮门槛。',context:[],relevant_document_ids:[`doc-${i+1}`]}))
 const packages=specs.map((s,i)=>({sample_id:s.case_id,question:s.query,current_answer:answers[i],necessary_history:[],reference_complete:true,missing_items:[],evidence:[{scope:'REFERENCE',evidence_id:`ref-${i+1}`,document_id:`doc-${i+1}`,text:refs[i]},{scope:'RETRIEVED',evidence_id:`chunk-${i+1}`,document_id:`doc-${i+1}`,text:refs[i]}],metadata:{ignored:'PACKAGE_METADATA_MUST_NOT_COPY'}}))
 const answerRows=specs.map((s,i)=>({case_id:s.case_id,execution_status:'SUCCESS',judge_status:'SUCCESS',original_status:i?'PASS':'FAIL',final_status:i?'PASS':'FAIL',original_reason:reasons[i],hard_rule_violations:[],scores:{},turn_evidence:[{turn:1,question:s.query,response:answers[i],tool_traces:[]}],evidence_evaluation:{status:'SUCCESS',judgment:{verdict:i?'PASS':'FAIL',reason:reasons[i],task_resolved:!!i,faithful_to_available:!!i,dimensions:{faithfulness:{score:i?2:0,reason:reasons[i],answer_quotes:[answers[i]],citations:[{scope:'REFERENCE',evidence_id:`ref-${i+1}`,quote:refs[i]}]}},critical_errors:i?[]:['unsupported_promise'],insufficient_items:[]}}}))
 const documents=refs.map((text,i)=>({document_id:`doc-${i+1}`,title:i?'玻璃杯规格':'包邮规则',text,metadata:{internal:'DOCUMENT_METADATA_MUST_NOT_COPY'}}))
 const knowledge={knowledge_dataset_id:'knowledge-check',name:'软件验收资料',version:1,documents}
 const index={index_id:'index-check',knowledge_dataset_id:'knowledge-check',knowledge_version:1,embedding_model:'sha256-lexical-bigram-v1',chunk_config:{chunk_size:200,chunk_overlap:20}}
 const evalSet={retrieval_eval_set_id:'evalset-check',version:1,index_id:'index-check',name:'软件验收评测',cases:specs,split_reviewed:true}
 return {run:{run_id:'run-check',name:'软件验收评测',run_type:'BASELINE',status:'COMPLETE',created_at:'2026-10-22T01:00:00Z',provider_session_id:'session-check',verify_answers:true,
  provider_configuration_snapshot:{model:'fixture',api_key:'PROVIDER_SECRET_MUST_NOT_COPY'},retrieval_config:{top_k:3,query_rewrite:false,rerank:false},
  controls:{knowledge_snapshot:knowledge,index_snapshot:index,eval_set_snapshot:evalSet,scoring_profile:{profile_id:'saved-profile',name:'保存的评分规则',calibration_status:'INITIAL_UNVALIDATED',rubric,protocol:{prompt:'对照参考资料判断回答，资料不足时应说明无法判断。'},judge_configuration:{api_key:'JUDGE_SECRET_MUST_NOT_COPY'}}},
  execution_order:specs.map(s=>s.case_id),case_results:specs.map((s,i)=>({case_id:s.case_id,query:s.query,results:[{chunk_id:`chunk-${i+1}`,document_id:`doc-${i+1}`,text:refs[i]}],input_package:packages[i],retrieval_status:'TOP_1_HIT',metrics:{relevant_rank:1,returned_relevant_rank:1},top_k:3})),answer_results:answerRows,metrics:{}},
  effective_answer_results:structuredClone(answerRows),trusted_result:{cases:[{case_id:'case-1',evaluation_state:'FAIL'},{case_id:'case-2',evaluation_state:'PASS'}],sample_flow:{coverage:{numerator:2,denominator:2},partial_pass_rate:{numerator:1,denominator:2}}}}
}

export function savedOperationsRow(){
 const view=savedScoreView()
 const p=view.run.case_results[0].input_package
 return {job:{job_id:'job-check',status:'COMPLETE',rule_snapshot:{name:'批次冻结规则',rubric:view.run.controls.scoring_profile.rubric,judge_prompt:'按批次保存的规则核对，不使用当前新规则。'}},
  row:{record:{sample_id:'case-1',question:p.question,answer:p.current_answer,reference_complete:false,reference_policy:[],retrieved_evidence:[],context:[]},event:{evaluation_state:'FAIL',reason:'批次保存的机器原判',input_package:structuredClone(p),judgment:view.run.answer_results[0].evidence_evaluation.judgment},review:{evaluation_state:'PASS',reason:'人评单独保留'}}}
}
