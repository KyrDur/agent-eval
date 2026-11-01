import MarkdownIt from 'markdown-it'

// Display only: saved answers, clipboard exports and evidence stay untouched.
const markdown=new MarkdownIt({html:false,breaks:true,linkify:true,typographer:false,maxNesting:32})
const validLink=markdown.validateLink.bind(markdown)
markdown.validateLink=url=>validLink(url)&&(!/^[a-z][a-z\d+.-]*:/i.test(url)||/^(https?:|mailto:)/i.test(url))
const openLink=markdown.renderer.rules.link_open||((tokens,index,options,env,renderer)=>renderer.renderToken(tokens,index,options))
markdown.renderer.rules.link_open=(tokens,index,options,env,renderer)=>{
 tokens[index].attrSet('target','_blank')
 tokens[index].attrSet('rel','noopener noreferrer')
 return openLink(tokens,index,options,env,renderer)
}
// Model answers must not silently load tracking images or remote resources.
markdown.renderer.rules.image=(tokens,index)=>markdown.utils.escapeHtml(tokens[index].content||'图片')
markdown.renderer.rules.table_open=()=>'<div class="markdown-table-scroll"><table>\n'
markdown.renderer.rules.table_close=()=>'</table></div>\n'
export function renderMarkdown(source){return markdown.render(String(source??''))}
