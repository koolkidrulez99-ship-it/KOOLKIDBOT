(function(){
"use strict";
const KEY="koolkidTabConceptV2";
let root=null, activeTab="auto";
const moved=new Map();
function isKoolkid(){try{return String(activeProfile||"").toUpperCase()==="KOOLKID";}catch(e){return false;}}
function saved(){try{return localStorage.getItem(KEY)==="1";}catch(e){return false;}}
function save(on){try{localStorage.setItem(KEY,on?"1":"0");}catch(e){}}
function move(node,target){if(!node||!target)return;if(!moved.has(node)){const marker=document.createComment("kk-concept-origin");if(node.parentNode)node.parentNode.insertBefore(marker,node);moved.set(node,marker);}target.appendChild(node);}
function restore(){for(const [node,marker] of moved){try{if(marker.parentNode){marker.parentNode.insertBefore(node,marker);marker.remove();}}catch(e){}}moved.clear();}
function shellHtml(){return `
<div id="kkConceptModeBar"><span>UI Concept</span><button id="kkConceptToggle" type="button">Try Tab Concept</button></div>
<div id="kkConceptWrap">
 <div class="kk-concept-head"><div class="kk-concept-head-title">⚙️ KOOLKID CONTROL PANEL</div><button id="kkConceptOriginal" type="button">Original UI</button></div>
 <div class="kk-concept-tabs">
  <button class="kk-concept-tab is-active" data-kkconcept-tab="auto">AUTO TRADE</button>
  <button class="kk-concept-tab" data-kkconcept-tab="manual">MANUAL TRADE</button>
  <button class="kk-concept-tab" data-kkconcept-tab="automated">AUTOMATED TRADING</button>
 </div>
 <section class="kk-concept-panel is-active" data-kkconcept-panel="auto"><div class="kk-concept-card"><div class="kk-concept-card-title">Auto Trade</div><div class="kk-concept-card-note">Auto modes, scanners and AI strategies only.</div><div id="kkConceptAuto" class="kk-concept-stack"></div></div></section>
 <section class="kk-concept-panel" data-kkconcept-panel="manual"><div class="kk-concept-card"><div class="kk-concept-card-title">Manual Trade</div><div class="kk-concept-card-note">Manual entries and quick trade buttons only.</div><div id="kkConceptManual" class="kk-concept-stack"></div></div></section>
 <section class="kk-concept-panel" data-kkconcept-panel="automated"><div class="kk-concept-card"><div class="kk-concept-card-title">Automated Trading</div><div class="kk-concept-card-note">Martingale, recovery and session automation only.</div><div id="kkConceptAutomated" class="kk-concept-stack"></div></div></section>
</div>`;}
function setTab(name){
 activeTab=["auto","manual","automated"].includes(name)?name:"auto";
 document.querySelectorAll(".kk-concept-tab").forEach(b=>b.classList.toggle("is-active",b.dataset.kkconceptTab===activeTab));
 document.querySelectorAll(".kk-concept-panel").forEach(p=>p.classList.toggle("is-active",p.dataset.kkconceptPanel===activeTab));
 const target=document.querySelector('.kk-concept-panel.is-active');
 if(target&&target.scrollIntoView)target.scrollIntoView({block:"nearest"});
}
function sharedNodes(setup){
 if(!setup)return[];
 const kids=[...setup.children];
 return kids.slice(0,5);
}
function manualPairBlock(){
 const btn=document.getElementById("koolkidPairManualPlaceBtn");
 if(!btn)return null;
 let node=btn.parentElement;
 while(node&&node.parentElement&&node.parentElement.id!=="koolkidPairRecoveryDropdown"){
   if(String(node.getAttribute("style")||"").includes("border-top"))return node;
   node=node.parentElement;
 }
 return btn.parentElement;
}
function place(){
 if(!root||!document.body.classList.contains("kk-concept-active"))return;
 const card=root.querySelector(":scope > .card"), grid=card&&card.querySelector(".panelGrid");
 if(!grid)return;
 const left=grid.children[0], right=grid.children[1];
 const setup=left&&left.children[0], stack=right&&right.querySelector(".ui-primary-stack");
 if(!setup||!stack)return;
 const auto=document.getElementById("kkConceptAuto"), manual=document.getElementById("kkConceptManual"), automated=document.getElementById("kkConceptAutomated");
 if(!auto||!manual||!automated)return;
 sharedNodes(setup).forEach(n=>move(n,document.querySelector('.kk-concept-panel[data-kkconcept-panel="'+activeTab+'"] .kk-concept-stack')));
 const setupKids=[...setup.children];
 const tpSlGroup=setupKids.find(n=>n.querySelector&&n.querySelector("#tp")&&n.querySelector("#sl"));
 const manualTp=[...setup.querySelectorAll("button")].find(b=>(b.textContent||"").trim()==="SET TP");
 const manualSl=[...setup.querySelectorAll("button")].find(b=>(b.textContent||"").trim()==="SET SL");
 move(tpSlGroup,manual);move(manualTp,manual);move(manualSl,manual);
 move(document.getElementById("autoSlBtn"),automated);
 move(document.getElementById("koolkidSingleMartingalePanel"),automated);
 move(document.getElementById("koolkidOver6ScanMartingalePanel"),automated);
 move(document.getElementById("koolkidBalancedRecoveryPanel"),automated);
 const stackKids=[...stack.children];
 const mainAutoGrid=stackKids[0], autoBtn=stackKids[1], dual=stackKids[2], burst=stackKids[3], autoStrategies=stackKids[4], advanced=stackKids[5], mpull=stackKids[6];
 const pairManual=manualPairBlock();
 const g1=document.getElementById("g1AutoBtnKoolkid"), half=document.getElementById("halfAutoBtnKoolkid");
 const pairBtn=document.getElementById("koolkidPairRecoveryBtnKoolkid"), pairDrop=document.getElementById("koolkidPairRecoveryDropdown");
 if(pairManual)move(pairManual,manual);
 move(g1,auto);move(pairBtn,automated);move(pairDrop,automated);move(half,manual);
 move(mainAutoGrid,auto);move(autoBtn,auto);move(autoStrategies,auto);move(advanced,auto);move(mpull,auto);
 move(document.getElementById("koolkidGoldenCardPromo"),auto);
 move(dual,manual);move(burst,manual);
}
function mount(){
 const next=document.getElementById("koolkidProfileUi");
 if(!next||!isKoolkid()){deactivate();return;}
 if(root!==next){restore();root=next;}
 if(!document.getElementById("kkConceptWrap")){
   root.insertAdjacentHTML("afterbegin",shellHtml());
   document.getElementById("kkConceptToggle").onclick=()=>apply(!document.body.classList.contains("kk-concept-active"),true);
   document.getElementById("kkConceptOriginal").onclick=()=>apply(false,true);
   document.querySelectorAll(".kk-concept-tab").forEach(b=>b.onclick=()=>{restore();setTab(b.dataset.kkconceptTab);place();});
 }
 apply(saved(),false);
}
function apply(on,persist){
 if(!root||!root.isConnected){mount();if(!root)return;}
 if(persist)save(on);
 if(!on)restore();
 document.body.classList.toggle("kk-concept-active",!!on);
 const btn=document.getElementById("kkConceptToggle");
 if(btn){btn.textContent=on?"Use Original UI":"Try Tab Concept";btn.classList.toggle("is-on",!!on);}
 if(on){setTab(activeTab);place();}
}
function deactivate(){restore();if(document.body)document.body.classList.remove("kk-concept-active");root=null;}
window.KoolkidGrokUI={mount,apply,deactivate,setTab};
const obs=new MutationObserver(()=>{const next=document.getElementById("koolkidProfileUi");if(next&&isKoolkid()&&next!==root)mount();else if((!next||!isKoolkid())&&root)deactivate();});
function boot(){obs.observe(document.body,{childList:true,subtree:true});mount();}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot,{once:true});else boot();
})();