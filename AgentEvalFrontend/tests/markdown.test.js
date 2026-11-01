import test from 'node:test'
import assert from 'node:assert/strict'
import {renderMarkdown} from '../src/markdown.js'

test('answers render Chinese emphasis, lists, headings, tables and code without changing their source',()=>{
 const source='# 退货说明\n\n1. **质量问题退货**：店铺承担。\n2. 运费 `15元`。\n\n> 先核实订单。\n\n| 原因 | 运费 |\n| --- | --- |\n| 质量问题 | 店铺承担 |\n\n```json\n{"refund": true}\n```'
 const html=renderMarkdown(source)
 for(const fragment of ['<h1>退货说明</h1>','<ol>','<strong>质量问题退货</strong>','<code>15元</code>','<blockquote>','markdown-table-scroll','<table>','<th>原因</th>','<code class="language-json">'])assert.ok(html.includes(fragment),fragment)
 assert.ok(source.includes('**质量问题退货**'))
 assert.equal(renderMarkdown('第一行\n第二行'),'<p>第一行<br>\n第二行</p>\n')
})
test('untrusted model HTML, script links, remote images and code are inert',()=>{
 const html=renderMarkdown('<img src=x onerror=alert(1)>\n\n<script>alert(1)</script>\n\n[危险](javascript:alert(1))\n\n[数据](data:text/html,test)\n\n![配图](https://example.com/track.png)\n\n```html\n<script>bad()</script>\n```')
 assert.ok(!/<(?:script|img)\b/i.test(html))
 assert.ok(!/href="(?:javascript|data):/i.test(html))
 assert.ok(!html.includes('src="https://example.com/track.png"'))
 assert.ok(html.includes('&lt;script&gt;bad()&lt;/script&gt;'))
 assert.ok(html.includes('配图'))
})
test('safe links are explicit, isolated new-tab links and plain text still displays',()=>{
 const html=renderMarkdown('[政策](https://example.com/policy)\n\n无格式的回答也能正常阅读。')
 assert.ok(html.includes('href="https://example.com/policy"'))
 assert.ok(html.includes('rel="noopener noreferrer"'))
 assert.ok(html.includes('target="_blank"'))
 assert.ok(html.includes('无格式的回答也能正常阅读。'))
 assert.equal(renderMarkdown(null),'')
})
