(function(){
"use strict";
const KEY="koolkidOrganizedUi";
let root=null,activeTab="auto";
const moved=new Map();
function isKoolkid(){try{return String(activeProfile||"").toUpperCase()==="KOOLKID";}catch(e){return false;}}
function saved(){try{return localStorage.getItem(KEY)==="1";}catch(e){return false;}}
function save(on){try{localStorage.setItem(KEY,on?"1":"0");}catch(e){}}
function move(node,target){if(!node||!target)return;if(!moved.has(node)){const mark=document.createComment("kk-org-origin");node.parentNode&&node.parentNode.insertBefore(mark,node);moved.set(node,mark);}target.appendChild(node);}
function restore(){for(const [node,mark] of moved){try{if(mark.parentNode){mark.parentNode.insertBefore(node,mark);mark.remove();}}catch(e){}}moved.clear();}
function shellHtml(){return `
<div id="kkOrgModeBar"><span>KOOLKID Layout</span><button id="kkOrgToggle" type="button">Try Organized UI</button></div>
<div id="kkOrgShell">
 <div class="kk-org-head"><div><div class="kk-org-title">KOOLKID Trading Hub</div><div class="kk-org-sub">Same buttons and logic, grouped by how you trade.</div></div><button id="kkOrgOriginal" type="button">Original UI</button></div>
 <div class="kk-org-setup"><div class="kk-org-setup-title">Shared Trade Setup</div><div id="kkOrgSharedSetup"></div></div>
 <div class="kk-org-tabs">
  <button class="kk-org-tab is-active" data-kkorg-tab="auto">AUTO TRADE</button>
  <button class="kk-org-tab" data-kkorg-tab="manual">MANUAL TRADE</button>
  <button class="kk-org-tab" data-kkorg-tab="automated">AUTOMATED TRADING</button>
 </div>
 <section class="kk-org-panel is-active" data-kkorg-panel="auto"><div class="kk-org-section"><h3>Auto Trade</h3><p>Pick and run your auto modes, scanners and AI strategies from one place.</p><div id="kkOrgAuto" class="kk-org-stack"></div></div></section>
 <section class="kk-org-panel" data-kkorg-panel="manual"><div class="kk-org-section"><h3>Manual Trade</h3><p>Manual and quick-entry buttons are grouped here.</p><div id="kkOrgManual" class="kk-org-stack"></div></div></section>
 <section class="kk-org-panel" data-kkorg-panel="automated"><div class="kk-org-section"><h3>Automated Trading</h3><p>Martingale, recovery and session-based automation tools.</p><div id="kkOrgAutomated" class="kk-org-stack"></div></div></section>
</div>`;}
function setTab(name){
 activeTab=["auto","manual","automated"].includes(name)?name:"auto";
 document.querySelectorAll(".kk-org-tab").forEach(b=>b.classList.toggle("is-active",b.dataset.kkorgTab===activeTab));
 document.querySelectorAll(".kk-org-panel").forEach(p=>p.classList.toggle("is-active",p.dataset.kkorgPanel===activeTab));
}
function place(){
 if(!root||!document.body.classList.contains("kk-org-active"))return;
 const card=root.querySelector(":scope > .card"), grid=card&&card.querySelector(".panelGrid");
 if(!grid)return;
 const left=grid.children[0],right=grid.children[1];
 const setup=left&&left.children[0], stack=right&&right.querySelector(".ui-primary-stack");
 if(!setup||!stack)return;
 const shared=document.getElementById("kkOrgSharedSetup"),auto=document.getElementById("kkOrgAuto"),manual=document.getElementById("kkOrgManual"),automated=document.getElementById("kkOrgAutomated");
 const setupKids=[...setup.children];
 setupKids.slice(0,5).forEach(n=>move(n,shared));
 [12,13,14,15].forEach(i=>move(setupKids[i],manual));
 move(document.getElementById("koolkidSingleMartingalePanel"),automated);
 move(document.getElementById("koolkidOver6ScanMartingalePanel"),automated);
 move(document.getElementById("koolkidBalancedRecoveryPanel"),automated);
 const stackKids=[...stack.children];
 if(stackKids[0])move(stackKids[0],auto);
 if(stackKids[1])move(stackKids[1],auto);
 if(stackKids[2])move(stackKids[2],manual);
 const burst=stackKids[3];
 if(burst){
   const g1=document.getElementById("g1AutoBtnKoolkid"),half=document.getElementById("halfAutoBtnKoolkid"),pairBtn=document.getElementById("koolkidPairRecoveryBtnKoolkid"),pairDrop=document.getElementById("koolkidPairRecoveryDropdown");
   move(g1,auto);move(pairBtn,automated);move(pairDrop,automated);move(burst,manual);move(half,manual);
 }
 [4,5,6].forEach(i=>{if(stackKids[i])move(stackKids[i],auto);});
 move(document.getElementById("koolkidGoldenCardPromo"),auto);
}
function mount(){
 const next=document.getElementById("koolkidProfileUi");
 if(!next||!isKoolkid()){deactivate();return;}
 if(root!==next){restore();root=next;}
 if(!document.getElementById("kkOrgShell")){
   root.insertAdjacentHTML("afterbegin",shellHtml());
   document.getElementById("kkOrgToggle").onclick=()=>apply(!document.body.classList.contains("kk-org-active"),true);
   document.getElementById("kkOrgOriginal").onclick=()=>apply(false,true);
   document.querySelectorAll(".kk-org-tab").forEach(b=>b.onclick=()=>setTab(b.dataset.kkorgTab));
 }
 apply(saved(),false);
}
function apply(on,persist){
 if(!root||!root.isConnected){mount();if(!root)return;}
 if(persist)save(on);
 document.body.classList.toggle("kk-org-active",!!on);
 const btn=document.getElementById("kkOrgToggle");
 if(btn){btn.textContent=on?"Use Original UI":"Try Organized UI";btn.classList.toggle("is-on",!!on);}
 if(on){place();setTab(activeTab);}else restore();
}
function deactivate(){restore();document.body&&document.body.classList.remove("kk-org-active");root=null;}
window.KoolkidGrokUI={mount,apply,deactivate,setTab};
const obs=new MutationObserver(()=>{const next=document.getElementById("koolkidProfileUi");if(next&&isKoolkid()&&next!==root)mount();else if((!next||!isKoolkid())&&root)deactivate();});
function boot(){obs.observe(document.body,{childList:true,subtree:true});mount();}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot,{once:true});else boot();
})();