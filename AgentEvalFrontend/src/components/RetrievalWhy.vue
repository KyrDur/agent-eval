<template>
 <section class="retrieval-rationale" aria-label="查找方式的用途与业界案例">
  <h3>为什么要查找资料，还要把资料分段？</h3>
  <p>这些设置影响客服能否找到正确规则，以及回答时能否读到规则的条件和例外。</p>
  <dl class="retrieval-reasons">
   <div><dt>按含义查找：应对不同说法</dt><dd>用户问“钱啥时回卡里？”，资料写“退款到账时效”。语义查找尝试识别这种表达关联；按词语查找可作为对照，用同一组题验证效果。</dd></div>
   <div><dt>把长资料分段：只取相关内容</dt><dd>一份手册可能同时包含配送、退货和保修。拆成小段后，可以分别查找相关条款，也有助于适应模型能读取的长度。</dd></div>
   <div><dt>相邻片段保留重叠：减少断开上下文</dt><dd>如果“可以退货”和“定制商品除外”被切在两段，少量重复文字有助于保留关联。重叠越多，存储和检索中的重复内容也越多。</dd></div>
  </dl>
  <details class="retrieval-industry"><summary v-track="{action:'knowledge.industry_examples',placement:'RetrievalWhy.control_01'}">看业界案例：阿里云百炼、百度客悦、微软 Azure AI Search</summary>
   <article><h4>阿里云百炼：先找到企业资料，再交给模型回答</h4><p>百炼的官方知识库流程会解析文档、分段、向量化并建立索引；在基础文档问答中，先找到相关片段，再由模型生成答案。就像客服先翻到退货规则，再回答顾客的问题。<a v-track="{action:'knowledge.reference',placement:'RetrievalWhy.control_02'}" href="https://help.aliyun.com/zh/model-studio/rag-knowledge-base" target="_blank" rel="noopener noreferrer">阿里云百炼官方说明 ↗</a></p><p class="muted">对应本次评测：分别检查“有没有找对规则”和“回答有没有遵守规则”。</p></article>
   <article><h4>百度客悦智能客服：分段长度与重叠也需要设置</h4><p>客悦支持自动分段，也提供最大分段长度和相邻分段重叠比例等自定义设置。客服回答时，系统查找与问题相关的片段，再交给大模型组织答案。官方建议不了解参数时先使用自动设置。<a v-track="{action:'knowledge.reference',placement:'RetrievalWhy.control_03'}" href="https://cloud.baidu.com/doc/ky/s/9mfnuivfd" target="_blank" rel="noopener noreferrer">百度客悦官方说明 ↗</a></p><p class="muted">对应本次评测：检查“拆封能退吗？”这类问题找到的片段，是否完整保留退货条件和例外；首次保持默认即可。</p></article>
   <article><h4>微软 Azure AI Search：长文档切分与上下文重叠</h4><p>微软的技术实践说明，把长文档切成小段可适应模型输入限制；让相邻片段保留少量重叠文字，有助于维持上下文，具体大小应结合资料和任务调整。<a v-track="{action:'knowledge.reference',placement:'RetrievalWhy.control_04'}" href="https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-chunk-documents" target="_blank" rel="noopener noreferrer">微软官方说明 ↗</a></p><p class="muted">对应本次评测：检查返回的片段是否同时包含关键规则、适用条件和例外。</p></article>
  </details>
  <p class="retrieval-starting-point">首次使用，无需另外连接查找资料的服务。每段 200 字符、重叠 20 字符是当前实验起点；是否适合你的资料，可以通过评测结果判断。</p>
 </section>
</template>
