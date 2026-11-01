// Fill missing internal grouping records without asking novices to invent IDs.
// Existing grouping and test purpose remain unchanged; confirmation stays explicit.
export async function completeCaseGroups(rows,client){
 if(rows.every(c=>c.group_id))return rows
 const grouped=await client.post('/retrieval-case-groups',{cases:rows})
 if(grouped.conflicts.length)throw new Error('相似题被分到了两种用途，请在“题目用途设置”中把它们放在同一侧。')
 const byId=new Map(grouped.cases.map(c=>[c.case_id,c]))
 return rows.map(c=>{
  const group=c.group_id||byId.get(c.case_id)?.group_id
  if(!group)throw new Error('未能整理题目记录，请重新保存。原题目仍然保留。')
  return {...c,group_id:group}
 })
}
