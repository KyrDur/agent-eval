import test from 'node:test'
import assert from 'node:assert/strict'
import {readableScoringReason} from '../src/scoring-language.js'
const evaluation={raw_output:JSON.stringify({dimensions:{actionability:{answer_fragment_ids:['A1'],evidence_fragment_ids:[]},faithfulness:{answer_fragment_ids:['A1','A2'],evidence_fragment_ids:['R1','R2','R5','P1']}}})}

test('selected answer and evidence identifiers have readable names without becoming retrieval ranks',()=>{
 assert.equal(readableScoringReason('A1 提供可执行下一步。',evaluation,'actionability'),'这段回答提供可执行下一步。')
 assert.equal(readableScoringReason('所选 R1-R5 与 P1 支持 A1、A2。',evaluation,'faithfulness'),'所选检索资料与评分参考资料支持回答片段。')
})
test('unknown codes and product identifiers are not rewritten as evidence',()=>{
 const text='型号 SKU-A1、A100、R99；A1 有说明。'
 assert.equal(readableScoringReason(text,evaluation,'actionability'),'型号 SKU-A1、A100、R99；这段回答有说明。')
 assert.equal(readableScoringReason('R1 缺失。',evaluation,'actionability'),'R1 缺失。')
})
test('missing or malformed saved output never guesses what an identifier means',()=>{
 for(const value of [null,{raw_output:'invalid'},{raw_output:'{}'},{raw_output:'{"dimensions":null}'}])
  assert.equal(readableScoringReason('A1 提供步骤。',value),'A1 提供步骤。')
})
test('raw logs and original reasons remain unchanged while fenced model output is supported',()=>{
 const saved=JSON.stringify(evaluation),reason='A1 提供下一步。'
 assert.equal(readableScoringReason(reason,{raw_output:'```json\n'+evaluation.raw_output+'\n```'},'actionability'),'这段回答提供下一步。')
 assert.equal(reason,'A1 提供下一步。');assert.equal(JSON.stringify(evaluation),saved)
})
