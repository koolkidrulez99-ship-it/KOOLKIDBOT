const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/js/profiles/human.js'), 'utf8');
function functionSource(name) {
  const declaration = new RegExp(`^  (?:async )?function ${name}\\(`, 'm').exec(source);
  assert.ok(declaration, `Missing function ${name}`);
  const rest = source.slice(declaration.index);
  const next = /\n  (?:async )?function /.exec(rest);
  assert.ok(next, `Missing boundary after ${name}`);
  return rest.slice(0, next.index);
}

async function testRejection(preserveAcceptedLeg) {
  const state = {running:true, inFlight:false, mode:'EVEN_ODD', runId:'test', pending:{}};
  const context = vm.createContext({
    HUMAN_PARITY_MARTINGALE_STATE:state,
    getHumanParityMartingalePlan:() => [{side:'EVEN',stake:0.35},{side:'ODD',stake:0.35}],
    readHumanParityInteger:() => 1,
    normalizeHumanParityMode:value => value,
    selectHumanParityTradeMarket:async () => 'stpRNG',
    updateHumanParityMartingalePanel:() => {},
    clearHumanParityVisibleBatch:() => {state.currentBatch=null;},
    postJSON:async () => {
      if (preserveAcceptedLeg) state.pending.EVEN.contractId = 'accepted';
      throw new Error('Contract unavailable');
    },
  });
  vm.runInContext(functionSource('money') + functionSource('sendHumanParityMartingaleRound'), context);
  await context.sendHumanParityMartingaleRound();
  assert.equal(state.running, false);
  assert.equal(state.inFlight, false);
  assert.equal(state.status, 'Contract unavailable');
  assert.deepEqual(Object.keys(state.pending), preserveAcceptedLeg ? ['EVEN'] : []);
  assert.equal(state.runId, preserveAcceptedLeg ? 'test' : '');
}

async function main() {
  await testRejection(false);
  await testRejection(true);
  const state = {sessionPnl:0, running:true, limitHit:false};
  const context = vm.createContext({
    HUMAN_PARITY_MARTINGALE_STATE:state,
    readHumanParitySettings:() => ({takeProfit:0,stopLoss:0.15}),
    stopHumanParityMarketScan:() => {},
  });
  vm.runInContext(['money','signedMoney','applyHumanParityTpSlAfterResult'].map(functionSource).join('\n'), context);
  assert.equal(context.applyHumanParityTpSlAfterResult(-0.35), true);
  assert.equal(state.status, 'SL reached at -$0.35. Martingale stopped.');
  assert.equal(state.sessionPnl, -0.35);
  assert.match(functionSource('updateHumanParityMartingalePanel'), /Session P\/L \$\{signedMoney\(/);
  console.log('3 targeted HUMAN parity UI tests passed');
}
main().catch(error => { console.error(error); process.exitCode=1; });
