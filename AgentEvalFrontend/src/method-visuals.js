// Short captions accompany symbolic drawings; they never describe measured gains.
export const methodVisuals={
 KNOWLEDGE_UPDATE:{title:'把正确资料放回知识库',caption:'根据本题参考答案补充，原资料保留。',steps:['参考答案','知识库','原题复测']},
 ANSWER_PROMPT_CHANGE:{title:'给回答加一道检查',caption:'勾选规则，自动加入回答要求。',steps:['原规则','追加要求','原题复测']},
 QUERY_REWRITE_TOGGLE:{title:'改写查询，再找资料',caption:'原问题不变，只调整查找用语。',steps:['用户问法','查找用语','找资料']},
 RERANK_TOGGLE:{title:'让相关资料站到前面',caption:'同一批候选，换一种排列。',steps:['同一批资料','重新排列','取前几条']},
 CHUNKING_CHANGE:{title:'重新切分文档，并重建索引',caption:'保留原文，重新生成资料片段（chunk），再建立新的检索索引。',steps:['原文不变','重新切成片段','建立新索引']},
 EMBEDDING_CHANGE:{title:'换一种方式理解资料',caption:'相同资料，使用另一匹配模型。',steps:['同一问题','换匹配方式','找资料']},
 RETRIEVAL_MODE_CHANGE:{title:'从另一条路找到资料',caption:'选择按词语、按含义，或两者一起找。',steps:['词语 / 含义','汇合查找','取资料']},
 CONTEXT_STRATEGY_CHANGE:{title:'连同前后文一起读',caption:'查到一段资料后，把它前后的说明一起给 AI，避免漏掉条件和例外。',steps:['前面的说明','查到的内容','后面的说明']},
 CANDIDATE_POOL_CHANGE:{title:'先多找一些，再挑',caption:'先找多少与最终给多少，分开调整。',steps:[]},
 TOP_K_CHANGE:{title:'调整最后给模型的资料',caption:'查找范围不变，调整最终参考条数。',steps:[]},
}
