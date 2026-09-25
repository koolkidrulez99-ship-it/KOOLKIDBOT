(function(){
"use strict";
const KEY="koolkidGrokUi";
let root=null, shell=null, modeBar=null, mainCard=null, panelGrid=null;
let activeTab="trade", hudTimer=null;
const moved=new Map();
function isKoolkid(){try{return String(activeProfile||"").toUpperCase()==="KOOLKID";}catch(e){return false;}}
function saved(){try{return localStorage.getItem(KEY)==="1";}catch(e){return false;}}
function save(on){try{localStorage.setItem(KEY,on?"1":"0");}catch(e){}}
function txt(ids,fallback){for(const id of ids){const e=document.getElementById(id);if(e){const v=String(e.textContent||e.value||"").trim();if(v)return v;}}return fallback;}
function move(node,target){if(!node||!target)return;if(!moved.has(node)){const mark=document.createComment("kk-grok-origin");node.parentNode&&node.parentNode.insertBefore(mark,node);moved.set(node,mark);}if(node.parentNode!==target)target.appendChild(node);}
function restore(){for(const [node,mark] of moved){try{if(mark.parentNode){mark.parentNode.insertBefore(node,mark);mark.remove();}}catch(e){}}moved.clear();}
function panel(id){return document.getElementById(id);}
function ensurePlacement(){
 if(!root||!document.body.classList.contains("kk-grok-active"))return;
 mainCard=root.querySelector(":scope > .card"); panelGrid=mainCard&&mainCard.querySelector(".panelGrid");
 if(!mainCard||!panelGrid)return;
 const left=panelGrid.children[0], right=panelGrid.children[1];
 move(document.getElementById("koolkidGoldenCardPromo"),panel("kkgTradeGolden"));
 move(left&&left.children[0],panel("kkgTradeSetup"));
 move(right&&right.querySelector(".ui-primary-stack"),panel("kkgStrategiesBody"));
 move(right&&right.children[0],panel("kkgAnalysisBody"));
 move(document.getElementById("koolkidConfidenceBarsBlock"),panel("kkgAnalysisBody"));
 move(document.getElementById("koolkidTradeHistoryCard"),panel("kkgHistoryBody"));
}
function setTab(name){
 activeTab=["trade","strategies","analysis","history"].includes(name)?name:"trade";
 document.querySelectorAll(".kkg-tab").forEach(b=>b.classList.toggle("is-active",b.dataset.tab===activeTab));
 document.querySelectorAll(".kkg-panel").forEach(p=>p.classList.toggle("is-active",p.dataset.panel===activeTab));
 ensurePlacement(); window.scrollTo({top:Math.max(0,(shell?.getBoundingClientRect().top||0)+window.scrollY-12),behavior:"smooth"});
}
function syncHud(){
 if(!shell||!document.body.classList.contains("kk-grok-active"))return;
 ensurePlacement();
 const symbol=document.getElementById("symbol");
 const market=symbol&&symbol.options&&symbol.selectedIndex>=0?String(symbol.options[symbol.selectedIndex].text||symbol.value):txt(["currentMarket","marketName"],"OFFLINE TAPE");
 const digit=txt(["lastDigitBox","lastDigit"],"-"), ticks=txt(["tickCount","tickCounter"],"0");
 const stakeEl=document.getElementById("stake"), stake=Number(stakeEl&&stakeEl.value);
 const bal=txt(["balance","balanceBox","currentBalance"],"$0.00");
 const pnl=txt(["netPnlBox","profileNetProfitLoss"],"$0.00");
 const set=(id,v)=>{const e=document.getElementById(id);if(e)e.textContent=v;};
 set("kkgMarket",market);set("kkgDigit",digit);set("kkgTicks",ticks);
 set("kkgStake",Number.isFinite(stake)?"$"+stake.toFixed(2):"$0.00");
 set("kkgBalance",/[$£€J]/.test(bal)?bal:"$"+bal);set("kkgPnl",/[$£€J]/.test(pnl)?pnl:"$"+pnl);
 const auto=txt(["autoBtn"],"Idle");set("kkgState",/ON/i.test(auto)?"Running":"Idle");
 const pn=document.getElementById("kkgPnl"),n=Number(String(pnl).replace(/[^0-9+.-]/g,""));
 if(pn){pn.classList.toggle("kkg-pnl-win",Number.isFinite(n)&&n>0);pn.classList.toggle("kkg-pnl-loss",Number.isFinite(n)&&n<0);}
}
function startHud(){stopHud();syncHud();hudTimer=setInterval(syncHud,650);}
function stopHud(){if(hudTimer)clearInterval(hudTimer);hudTimer=null;}
function openProfiles(){const b=document.getElementById("koolkidBtn");if(b&&b.parentElement)b.parentElement.scrollIntoView({behavior:"smooth",block:"center"});}
function shellHtml(){
 return `<div id="kkGrokModeBar"><span>KOOLKID UI</span><button id="kkGrokToggle" type="button">Try Grok UI</button></div>
 <div id="kkGrokShell">
  <div class="kkg-head"><div class="kkg-brand"><div class="kkg-logo">X</div><div><div class="kkg-title">KOOLKID</div><div class="kkg-sub">Digit hunter · Under 9 bias</div></div></div>
   <div class="kkg-head-actions"><button id="kkgProfiles" type="button">⚡ Profiles</button><button id="kkgOriginal" type="button" title="Use original UI">▣</button></div></div>
  <div class="kkg-tape"><div class="kkg-tape-top"><span id="kkgMarket" class="kkg-market">OFFLINE TAPE</span><span id="kkgState" class="kkg-state">Idle</span></div>
   <div class="kkg-stats"><div class="kkg-stat"><label>Digit</label><strong id="kkgDigit">-</strong></div><div class="kkg-stat"><label>Ticks</label><strong id="kkgTicks">0</strong></div>
   <div class="kkg-stat"><label>Stake</label><strong id="kkgStake">$1.00</strong></div><div class="kkg-stat"><label>Balance</label><strong id="kkgBalance">$0.00</strong></div>
   <div class="kkg-stat"><label>P/L</label><strong id="kkgPnl">$0.00</strong></div></div></div>
  <div class="kkg-tabs"><button class="kkg-tab is-active" data-tab="trade">⌖<br>Trade</button><button class="kkg-tab" data-tab="strategies">▦<br>Strategies</button><button class="kkg-tab" data-tab="analysis">⌁<br>Analysis</button><button class="kkg-tab" data-tab="history">↶<br>History</button></div>
  <section class="kkg-panel is-active" data-panel="trade"><div class="kkg-card"><div class="kkg-section-title">Trading setup</div><div class="kkg-section-note">Same KOOLKID controls, arranged in the compact dashboard layout.</div><div id="kkgTradeSetup"></div></div><div class="kkg-section-label">Highest Conviction</div><div id="kkgTradeGolden"></div></section>
  <section class="kkg-panel" data-panel="strategies"><div class="kkg-section-title">Strategies</div><div class="kkg-section-note">Arm and configure the same live KOOLKID strategies.</div><div id="kkgStrategiesBody"></div></section>
  <section class="kkg-panel" data-panel="analysis"><div class="kkg-section-title">Analysis</div><div class="kkg-section-note">Live digit distribution, confidence and barrier analysis.</div><div id="kkgAnalysisBody"></div></section>
  <section class="kkg-panel" data-panel="history"><div class="kkg-section-title">History</div><div class="kkg-section-note">KOOLKID results and trade history.</div><div id="kkgHistoryBody"></div></section>
 </div>`;
}
function mount(){
 const next=document.getElementById("koolkidProfileUi"); if(!next||!isKoolkid()){deactivate();return;}
 if(root!==next){restore();root=next;shell=null;modeBar=null;}
 if(!document.getElementById("kkGrokShell")){
   root.insertAdjacentHTML("afterbegin",shellHtml()); shell=document.getElementById("kkGrokShell");modeBar=document.getElementById("kkGrokModeBar");
   document.getElementById("kkGrokToggle").onclick=()=>apply(!document.body.classList.contains("kk-grok-active"),true);
   document.getElementById("kkgOriginal").onclick=()=>apply(false,true);document.getElementById("kkgProfiles").onclick=openProfiles;
   document.querySelectorAll(".kkg-tab").forEach(b=>b.onclick=()=>setTab(b.dataset.tab));
 }else{shell=document.getElementById("kkGrokShell");modeBar=document.getElementById("kkGrokModeBar");}
 apply(saved(),false);
}
function apply(on,persist){
 if(!root||!root.isConnected){mount();if(!root)return;}
 if(persist)save(on);document.body.classList.toggle("kk-grok-active",!!on);
 const btn=document.getElementById("kkGrokToggle");if(btn){btn.textContent=on?"Use Original UI":"Try Grok UI";btn.classList.toggle("is-on",!!on);}
 if(on){ensurePlacement();setTab(activeTab);startHud();}else{stopHud();restore();}
}
function deactivate(){stopHud();restore();document.body&&document.body.classList.remove("kk-grok-active");root=null;shell=null;modeBar=null;}
window.KoolkidGrokUI={mount,apply,deactivate,setTab,syncHud};
const obs=new MutationObserver(()=>{const next=document.getElementById("koolkidProfileUi");if(next&&isKoolkid()&&next!==root)mount();else if((!next||!isKoolkid())&&root)deactivate();});
function boot(){obs.observe(document.body,{childList:true,subtree:true});mount();}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot,{once:true});else boot();
})();