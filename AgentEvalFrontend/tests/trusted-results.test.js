import {test} from 'node:test'
import assert from 'node:assert/strict'
import {ratioText,comparisonMessage} from '../src/trusted-results.js'
test('Zero or missing denominators never become zero percent',()=>{
 assert.match(ratioText({numerator:0,denominator:0,value:null}),/不可计算/)
 assert.match(ratioText(null),/不可计算/)
 assert.equal(ratioText({numerator:6,denominator:10,value:.6}),'6 / 10 · 60.0%')
})
test('Coverage loss remains an explicit restriction even if pass rate rises',()=>{
 const message=comparisonMessage({overall_improvement_allowed:false,restriction_reasons:['VALID_DECISION_COVERAGE_DECLINED']})
 assert.match(message,/能判断的题变少/);assert.match(message,/不能只看剩下的题/)
 assert.match(comparisonMessage(null),/历史比较/)
})
