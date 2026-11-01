import test from 'node:test'
import assert from 'node:assert/strict'
import {copyCompleteText} from '../src/clipboard-copy.js'

test('one copy preserves a large Unicode log and restores focus without leaving a hidden field',async()=>{
 const text='完整记录🙂\n'.repeat(300000)
 let field,copied,removed=false,focused=false,range
 const document={activeElement:{focus:()=>{focused=true}},body:{appendChild:node=>{field=node}},createElement:()=>({style:{},setAttribute(){},select(){},setSelectionRange:(...r)=>{range=r},remove(){removed=true}}),execCommand:()=>{copied=field.value;return true}}
 await copyCompleteText(text,{document,clipboard:{writeText(){throw new Error('not needed')}}})
 assert.equal(copied,text);assert.deepEqual(range,[0,text.length]);assert.equal(removed,true);assert.equal(focused,true)
})
test('a blocked synchronous copy falls back with the whole original text',async()=>{
 const text='第一条\n🙂最后一条',received=[]
 const document={body:{appendChild(){}},createElement:()=>({style:{},setAttribute(){},select(){},setSelectionRange(){},remove(){}}),execCommand:()=>false}
 await copyCompleteText(text,{document,clipboard:{writeText:async value=>{received.push(value)}}})
 assert.deepEqual(received,[text])
})
test('a clipboard that never responds rejects so the UI can offer a full file instead of hanging',async()=>{
 await assert.rejects(copyCompleteText('完整内容',{document:undefined,clipboard:{writeText:()=>new Promise(()=>{})},timeoutMs:10}),/clipboard timeout/)
})
