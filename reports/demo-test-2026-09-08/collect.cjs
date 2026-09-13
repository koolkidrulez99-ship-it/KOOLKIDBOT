const fs = require('node:fs');
const path = require('node:path');
const safe = value => {
  if (Array.isArray(value)) return value.map(safe);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k,v]) => [k, /token|password|secret|authorization|cookie|otp|loginid|account_id|client_id|username|email|url/i.test(k) ? '[REDACTED]' : safe(v)]));
  if (typeof value === 'string') return value.replace(/(?:D|R)OT\d+|VRTC\d+|CR\d+/g, '[ACCOUNT REDACTED]').replace(/Bearer\s+\S+/gi,'Bearer [REDACTED]').replace(/https?:\/\/\S+|wss?:\/\/\S+/gi,'[URL REDACTED]');
  return value;
};
const source = fs.readFileSync('C:/Users/jjmje/AppData/Local/Temp/koolkid-login-preview-stderr.log','utf8');
const entries = [];
const windows = [
  ['2026-09-08 11:25:00','2026-09-08 11:43:30'],
  ['2026-09-08 22:13:00','2026-09-08 22:23:15'],
  ['2026-09-09 02:44:48','2026-09-09 03:26:16'],
];
for (const line of source.split(/\r?\n/)) {
  if (!windows.some(([from,to]) => line.slice(0,19) >= from && line.slice(0,19) <= to) || !line.includes('[db5534ba-d1bf-4880-836a-77b5ff73bcb0]')) continue;
  const markerMatch = line.match(/proposal_about_to_be_sent|final_proposal_payload|deriv_proposal_response_raw|deriv_proposal_error_raw|deriv_contracts_for_(?:send|response)|deriv_raw_error|unchain_\w*(?:validated|blocked)|active_symbols_(?:send|response)|buy_actually_sent|buy_using_proposal|deriv_options_otp_success|pat_options_websocket_open_waiting_balance|pat_options_balance_authenticated|deriv_trade_oauth_blocked/);
  if (!markerMatch) continue;
  const at = line.slice(0,23);
  const marker = markerMatch[0];
  const match = line.match(/(?:raw|response|payload|proposal)=(\{.*\})$/);
  if (match) {
    try { entries.push({ at, marker, data:safe(JSON.parse(match[1])) }); }
    catch { entries.push({ at, marker, note:'Payload could not be parsed; raw text omitted.' }); }
  } else entries.push({ at, marker, message:safe(line.replace(/\[[0-9a-f-]{36}\]/g,'[TEST SESSION]')) });
}
fs.writeFileSync(path.join(__dirname,'protocol.jsonl'),entries.map(x=>JSON.stringify(x)).join('\n')+'\n');
const evidencePath=path.join(__dirname,'evidence.jsonl');
const evidence=fs.readFileSync(evidencePath,'utf8').trim().split('\n').map(line=>safe(JSON.parse(line)));
fs.writeFileSync(evidencePath,evidence.map(x=>JSON.stringify(x)).join('\n')+'\n');
console.log(JSON.stringify({protocolRecords:entries.length, proposalCount:entries.filter(x=>x.data?.proposal===1).length, recentProposals:entries.filter(x=>x.data?.proposal===1).slice(-4).map(x=>x.data), recentErrors:entries.filter(x=>x.data?.error && x.data?.msg_type==='proposal').slice(-2).map(x=>x.data)}));
