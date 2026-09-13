const fs = require('node:fs');
const path = require('node:path');
const read = name => fs.readFileSync(path.join(__dirname,name),'utf8').trim().split('\n').filter(Boolean).map(JSON.parse);
const evidence = read('evidence.jsonl');
const starts = evidence.filter(e=>e.kind==='test_start');
const ends = evidence.filter(e=>e.kind==='test_end');
const placed = new Map();
const settled = new Map();
for (const record of evidence) {
  const events = record.events || (record.kind==='events' ? record.data : []);
  for (const e of events || []) {
    if (e.event==='trade_placed') placed.set(String(e.data.contract_id),e.data);
    if (e.event==='trade_result') settled.set(String(e.data.contract_id),e.data);
  }
}
const mismatches = [];
for (const [id,p] of placed) {
  const result = settled.get(id);
  if (!result) continue;
  const fields = ['type','contract_type','mode','batch_id','dual_market_batch_id','dual_market_leg_index'];
  const differences = fields.filter(k => (p[k] ?? null) !== (result[k] ?? null));
  if (differences.length) mismatches.push({contract_id:id,differences,placement:Object.fromEntries(fields.map(k=>[k,p[k]??null])),settlement:Object.fromEntries(fields.map(k=>[k,result[k]??null]))});
}
const protocol=read('protocol.jsonl');
const errors = new Map(protocol.filter(e=>e.data?.error && e.data.msg_type==='proposal').map(e=>[e.data.req_id,e.data]));
const summary = {
  status:'Paused: local server restarted and login page reopened at 2026-09-09 15:31 UTC; awaiting demo reconnection',
  firstLiveTest:starts[0]?.at,
  baseline:starts[0]?.baseline,
  lastRecordedBalance:ends.at(-1)?.balance,
  lastCompletedLiveTest:ends.at(-1)?.at,
  placements:placed.size,
  settlements:settled.size,
  wins:[...settled.values()].filter(t=>t.profit>0).length,
  losses:[...settled.values()].filter(t=>t.profit<0).length,
  netPnl:Number([...settled.values()].reduce((n,t)=>n+Number(t.profit||0),0).toFixed(2)),
  totalStake:Number([...placed.values()].reduce((n,t)=>n+Number(t.stake||0),0).toFixed(2)),
  unsettledObservedIds:[...placed.keys()].filter(id=>!settled.has(id)),
  metadataMismatches:mismatches,
  proposalErrorCount:errors.size,
  completedCases:ends.map(e=>({name:e.test,at:e.at,balance:e.balance,placements:(e.events||[]).filter(v=>v.event==='trade_placed').length})),
  remainingProfiles:['Mutant AUTO blocked by UI; manual cases already attempted','CLOUD live start blocked; read-only status/UI already inspected'],
  sourceFilesChanged:false,
};
fs.writeFileSync(path.join(__dirname,'summary.json'),JSON.stringify(summary,null,2)+'\n');
console.log(JSON.stringify({...summary,metadataMismatches:mismatches.length,completedCases:summary.completedCases.length}));
