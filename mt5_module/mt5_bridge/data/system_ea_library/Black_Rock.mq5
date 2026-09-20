//+------------------------------------------------------------------+
//| Black Rock EA                                                 |
//| H4 market bias + M15 structure, trendline-break and level retest |
//+------------------------------------------------------------------+
#property copyright "Black Rock"
#property version   "2.00"
#property strict

#define BIAS_TF PERIOD_H4
#define EXEC_TF PERIOD_M15

enum Direction { DIR_NONE=0, DIR_BUY=1, DIR_SELL=-1 };
enum ReversalStage { STAGE_SCAN=0, STAGE_WAIT_SHIFT, STAGE_WAIT_RETEST };
struct Swing { datetime time; double price; };

input string InpStructure = "===== H4 BIAS / M15 CONFIRMATION =====";
input int H4SwingStrength = 2;
input int M15SwingStrength = 2;
input int StructureLookbackBars = 250;
input int LevelTolerancePoints = 50;
input int SRZoneWidthPoints = 300;
input int TrendlineBreakBufferPoints = 10;
input bool RequireH4Alignment = true; // enable only when H4 must already agree with the M15 reversal

input string InpRisk = "===== TRADE MANAGEMENT =====";
input double RiskPercent = 1.0;
input double TargetRR = 12.0;
input int StopBufferPoints = 0;
input int MaxSpreadPoints = 30;
input int MaxSlippagePoints = 20;
input bool UseSessionFilter = false;
input int SessionStartHour = 7;
input int SessionEndHour = 20;

input string InpGeneral = "===== GENERAL =====";
input long MagicNumber = 9122026;
input string TradeComment = "KKBOT(BLACK ROCK)";
input bool EnableChartObjects = true;
input bool DebugMode = true;
input bool EnableAutomatedEntries=true;
bool g_runtimeEntries=true;
input bool MoveToBreakEvenAt1R=true;
input int BreakEvenBufferPoints=0;
input bool EnableRRTrail=true;
input double TrailStartRR=1.5;
input double TrailDistanceRR=0.5;
datetime g_acceptedSetupTime=0;
string g_executionStatus="Waiting for Human Apostle setup";

input string InpAlerts = "===== ALERTS =====";
input bool EnablePopupAlerts = true;
input bool EnablePushAlerts = false;
input bool EnableEmailAlerts = false;
input bool AlertOnBiasChange = true;
input bool AlertOnSetup = true;
input bool AlertOnTrade = true;

Direction g_h4Bias=DIR_NONE, g_m15Bias=DIR_NONE;
Swing g_h4Highs[],g_h4Lows[],g_m15Highs[],g_m15Lows[];
datetime g_lastH4Bar=0,g_lastM15Bar=0;
bool g_waitingRetest=false;
ReversalStage g_reversalStage=STAGE_SCAN;
Direction g_setupDir=DIR_NONE;
double g_breakLevel=0;
double g_reversalStop=0;
double g_protectedStructure=0;
datetime g_breakTime=0;

void Log(string message) { g_executionStatus=message; if(DebugMode) Print("[BlackRock] ",message); }
string DirText(Direction d) { return d==DIR_BUY ? "BULLISH" : d==DIR_SELL ? "BEARISH" : "NEUTRAL"; }
void Notify(string eventName,string details)
  {
   string m="Black Rock ["+_Symbol+"] "+eventName+": "+details;
   Print("[BlackRock] ",m);
   if(EnablePopupAlerts) Alert(m);
   if(EnablePushAlerts) SendNotification(m);
   if(EnableEmailAlerts) SendMail("Black Rock - "+eventName,m);
  }
double Pt() { return _Point; }

bool InSession()
  {
   if(!UseSessionFilter) return true;
   MqlDateTime now; TimeToStruct(TimeCurrent(),now);
   if(SessionStartHour<=SessionEndHour) return now.hour>=SessionStartHour && now.hour<SessionEndHour;
   return now.hour>=SessionStartHour || now.hour<SessionEndHour;
  }
bool SpreadOK() { return (double)SymbolInfoInteger(_Symbol,SYMBOL_SPREAD)<=MaxSpreadPoints; }
bool IsFractalHigh(ENUM_TIMEFRAMES tf,int shift,int strength)
  {
   double p=iHigh(_Symbol,tf,shift);
   for(int i=1;i<=strength;i++) if(iHigh(_Symbol,tf,shift-i)>=p || iHigh(_Symbol,tf,shift+i)>=p) return false;
   return true;
  }
bool IsFractalLow(ENUM_TIMEFRAMES tf,int shift,int strength)
  {
   double p=iLow(_Symbol,tf,shift);
   for(int i=1;i<=strength;i++) if(iLow(_Symbol,tf,shift-i)<=p || iLow(_Symbol,tf,shift+i)<=p) return false;
   return true;
  }
void AddSwing(Swing &list[],datetime t,double p)
  {
   int n=ArraySize(list); ArrayResize(list,n+1); list[n].time=t; list[n].price=p;
  }
void CollectSwings(ENUM_TIMEFRAMES tf,int strength,Swing &highs[],Swing &lows[])
  {
   ArrayResize(highs,0); ArrayResize(lows,0);
   int bars=iBars(_Symbol,tf); int maxShift=MathMin(StructureLookbackBars,bars-strength-1);
   for(int s=maxShift;s>=strength;s--)
     {
      if(IsFractalHigh(tf,s,strength)) AddSwing(highs,iTime(_Symbol,tf,s),iHigh(_Symbol,tf,s));
      if(IsFractalLow(tf,s,strength)) AddSwing(lows,iTime(_Symbol,tf,s),iLow(_Symbol,tf,s));
     }
  }
Direction ReadStructure(ENUM_TIMEFRAMES tf,Swing &highs[],Swing &lows[],Direction previous)
  {
   int nh=ArraySize(highs),nl=ArraySize(lows); if(nh<2 || nl<2) return DIR_NONE;
   double close=iClose(_Symbol,tf,1);
   if(close>highs[nh-1].price) return DIR_BUY;
   if(close<lows[nl-1].price) return DIR_SELL;
   if(highs[nh-1].price>highs[nh-2].price && lows[nl-1].price>lows[nl-2].price) return DIR_BUY;
   if(highs[nh-1].price<highs[nh-2].price && lows[nl-1].price<lows[nl-2].price) return DIR_SELL;
   return previous;
  }
bool HasOurPosition()
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     { ulong t=PositionGetTicket(i); if(PositionSelectByTicket(t) && PositionGetString(POSITION_SYMBOL)==_Symbol && PositionGetInteger(POSITION_MAGIC)==MagicNumber) return true; }
   return false;
  }
double LineAt(const Swing &a,const Swing &b,datetime t)
  {
   if(a.time==b.time) return a.price;
   return a.price+(b.price-a.price)*(double)(t-a.time)/(double)(b.time-a.time);
  }
// For a long, price must break a descending M15 swing-high trendline; inverse for shorts.
bool TrendlineBreakAgrees(Direction dir)
  {
   double close=iClose(_Symbol,EXEC_TF,1),buffer=TrendlineBreakBufferPoints*Pt(); datetime t=iTime(_Symbol,EXEC_TF,1);
   int nh=ArraySize(g_m15Highs),nl=ArraySize(g_m15Lows);
   if(dir==DIR_BUY && nh>=2 && g_m15Highs[nh-1].price<g_m15Highs[nh-2].price)
      return close>LineAt(g_m15Highs[nh-2],g_m15Highs[nh-1],t)+buffer;
   if(dir==DIR_SELL && nl>=2 && g_m15Lows[nl-1].price>g_m15Lows[nl-2].price)
      return close<LineAt(g_m15Lows[nl-2],g_m15Lows[nl-1],t)-buffer;
   return false;
  }
void ResetSetup() { g_waitingRetest=false; g_reversalStage=STAGE_SCAN; g_setupDir=DIR_NONE; g_breakLevel=0; g_reversalStop=0; g_protectedStructure=0; g_breakTime=0; }
bool PriorTrendlineBroken(Direction prior)
  {
   int nh=ArraySize(g_m15Highs),nl=ArraySize(g_m15Lows); datetime t=iTime(_Symbol,EXEC_TF,1); double c=iClose(_Symbol,EXEC_TF,1),b=TrendlineBreakBufferPoints*Pt();
   if(prior==DIR_BUY)
      for(int i=nl-1;i>=1;i--) if(g_m15Lows[i].price>g_m15Lows[i-1].price) return c<LineAt(g_m15Lows[i-1],g_m15Lows[i],t)-b;
   if(prior==DIR_SELL)
      for(int i=nh-1;i>=1;i--) if(g_m15Highs[i].price<g_m15Highs[i-1].price) return c>LineAt(g_m15Highs[i-1],g_m15Highs[i],t)+b;
   return false;
  }
void ProcessReversal(Direction previousM15Bias)
  {
   if(HasOurPosition()) return;
   double close=iClose(_Symbol,EXEC_TF,1); int nh=ArraySize(g_m15Highs),nl=ArraySize(g_m15Lows);
   // 1) A close must break the existing HL/LH wick trendline.
   if(g_reversalStage==STAGE_SCAN && previousM15Bias!=DIR_NONE && PriorTrendlineBroken(previousM15Bias))
     {
      if(previousM15Bias==DIR_BUY && nl>0 && nh>=2)
        { g_setupDir=DIR_SELL; g_protectedStructure=g_m15Lows[nl-1].price; g_reversalStop=MathMax(g_m15Highs[nh-2].price,g_m15Highs[nh-1].price); g_reversalStage=STAGE_WAIT_SHIFT; }
      else if(previousM15Bias==DIR_SELL && nh>0 && nl>=2)
        { g_setupDir=DIR_BUY; g_protectedStructure=g_m15Highs[nh-1].price; g_reversalStop=MathMin(g_m15Lows[nl-2].price,g_m15Lows[nl-1].price); g_reversalStage=STAGE_WAIT_SHIFT; }
      else return;
      g_breakTime=iTime(_Symbol,EXEC_TF,1);
      if(AlertOnSetup) Notify("trendline broken",(g_setupDir==DIR_SELL?"Bullish HL trendline broke. Waiting for LL structure shift.":"Bearish LH trendline broke. Waiting for HH structure shift."));
      return;
     }
   // 2) The protected HL/LH must break. That creates the LL/LH or HH/HL reversal and defines the key level.
   if(g_reversalStage==STAGE_WAIT_SHIFT)
     {
      bool shifted=(g_setupDir==DIR_SELL ? close<g_protectedStructure : close>g_protectedStructure);
      if(!shifted) return;
      if(RequireH4Alignment && g_h4Bias!=g_setupDir) { ResetSetup(); return; }
      g_breakLevel=g_protectedStructure; g_waitingRetest=true; g_reversalStage=STAGE_WAIT_RETEST; g_breakTime=iTime(_Symbol,EXEC_TF,1);
      if(AlertOnSetup) Notify("structure shift confirmed",(g_setupDir==DIR_SELL?"LL formed. Support is now the sell retest level.":"HH formed. Resistance is now the buy retest level."));
     }
  }
double LotSize(double riskMoney,double stopDistance)
  {
   double ts=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE),tv=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE);
   double min=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN),max=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX),step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   if(ts<=0 || tv<=0 || stopDistance<=0 || step<=0) return 0;
   double lots=MathFloor((riskMoney/(stopDistance/ts*tv))/step)*step;
   if(lots<min) return 0; return MathMin(lots,max);
  }
ENUM_ORDER_TYPE_FILLING FillingMode()
  {
   long modes=SymbolInfoInteger(_Symbol,SYMBOL_FILLING_MODE);
   if((modes & SYMBOL_FILLING_FOK)==SYMBOL_FILLING_FOK) return ORDER_FILLING_FOK;
   if((modes & SYMBOL_FILLING_IOC)==SYMBOL_FILLING_IOC) return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
  }
double RoundPrice(double price,bool down)
  {
   double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   if(tick<=0) return 0;
   return NormalizeDouble((down?MathFloor(price/tick+1e-8):MathCeil(price/tick-1e-8))*tick,_Digits);
  }
void ExecuteRetest()
  {
   if(!g_waitingRetest) return;
   if(g_m15Bias!=g_setupDir || (RequireH4Alignment && g_h4Bias!=g_setupDir)) { ResetSetup(); return; }
   if(!g_runtimeEntries || HasOurPosition() || g_acceptedSetupTime==g_breakTime) return;
   // The original structure-shift alert is the trigger: no further candle,
   // touch, rejection, spread, session, or second bias confirmation.
   MqlTick q={}; if(!SymbolInfoTick(_Symbol,q) || q.ask<=0 || q.bid<=0) return;
   bool buy=g_setupDir==DIR_BUY;
   double entry=buy?q.ask:q.bid;
   if(g_reversalStop<=0) { Log("Waiting: original structural stop unavailable"); return; }
   double sl=RoundPrice(g_reversalStop+(buy?-1:1)*StopBufferPoints*Pt(),buy);
   double minStop=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*Pt();
   double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   if(sl<=0 || tick<=0) return;
   // Keep the requested structural SL; retry if the broker cannot accept it yet.
   if(buy ? sl>=q.bid || q.bid-sl<minStop : sl<=q.ask || sl-q.ask<minStop) { Log("Waiting: structural SL is not currently broker-valid"); return; }
   double risk=buy?entry-sl:sl-entry;
   if(risk<=0) return;
   double tp=RoundPrice(entry+(buy?1:-1)*risk*TargetRR,!buy);
   if(tp<=0) { Log("Waiting: target price must be positive"); return; }
   double lots=LotSize(AccountInfoDouble(ACCOUNT_EQUITY)*RiskPercent/100.0,risk);
   if(lots<=0) { Log("Waiting: risk-sized volume below broker minimum"); return; }
   MqlTradeRequest request={}; MqlTradeResult result={};
   request.action=TRADE_ACTION_DEAL; request.symbol=_Symbol; request.magic=(ulong)MagicNumber;
   request.volume=lots; request.type=buy?ORDER_TYPE_BUY:ORDER_TYPE_SELL; request.price=entry;
   request.sl=sl; request.tp=tp; request.deviation=MaxSlippagePoints; request.comment=TradeComment;
   request.type_filling=FillingMode(); request.type_time=ORDER_TIME_GTC;
   bool ok=OrderSend(request,result);
   if(!ok || (result.retcode!=TRADE_RETCODE_DONE && result.retcode!=TRADE_RETCODE_DONE_PARTIAL && result.retcode!=TRADE_RETCODE_PLACED))
     { Log("Order deferred: "+IntegerToString((int)result.retcode)+" "+result.comment); return; }
   if(AlertOnTrade) Notify("entry accepted",(buy?"BUY":"SELL")+" "+DoubleToString(lots,2)+" lots | SL "+DoubleToString(sl,_Digits)+" | TP "+DoubleToString(tp,_Digits));
   g_acceptedSetupTime=g_breakTime; g_executionStatus="Entry accepted; managing structural SL";
  }
// Bruce thresholds, with immutable initial risk and broker-aware tightening.
string InitialRiskKey(ulong identifier)
{
 uint server=2166136261; string name=AccountInfoString(ACCOUNT_SERVER);
 for(int i=0;i<StringLen(name);i++) server=(server^(uint)StringGetCharacter(name,i))*16777619;
 return "BRR_"+IntegerToString((long)server)+"_"+IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN))+"_"+IntegerToString((long)identifier);
}
double InitialPositionRisk(ulong identifier,double entry,bool buy)
{
 string key=InitialRiskKey(identifier);
 if(GlobalVariableCheck(key)) return GlobalVariableGet(key);
 if(!HistorySelectByPosition(identifier)) return 0;
 for(int i=0;i<HistoryDealsTotal();i++)
 {
  ulong deal=HistoryDealGetTicket(i);
  if(HistoryDealGetInteger(deal,DEAL_ENTRY)!=DEAL_ENTRY_IN || HistoryDealGetInteger(deal,DEAL_MAGIC)!=MagicNumber) continue;
  ulong order=(ulong)HistoryDealGetInteger(deal,DEAL_ORDER);
  double initialSL=HistoryOrderGetDouble(order,ORDER_SL);
  double risk=buy?entry-initialSL:initialSL-entry;
  if(initialSL>0 && risk>0 && MathIsValidNumber(risk))
  { GlobalVariableSet(key,risk); GlobalVariablesFlush(); return risk; }
 }
 return 0; // Do not infer original R from a stop already moved to break-even.
}
double ManagedStop(bool buy,double entry,double currentSL,double initialRisk,double price,double tick,double minimumGap,
                   bool useBE,int beBuffer,bool useTrail,double startRR,double distanceRR)
{
 if(initialRisk<=0 || tick<=0 || price<=0) return 0;
 double progress=(buy?price-entry:entry-price)/initialRisk,candidate=currentSL;
 bool proposed=false;
 if(useBE && progress>=1.0)
 {
  double be=entry+(buy?1:-1)*beBuffer*_Point;
  if(candidate==0 || (buy?be>candidate:be<candidate)) { candidate=be; proposed=true; }
 }
 if(useTrail && progress>=startRR)
 {
  double trail=price+(buy?-1:1)*distanceRR*initialRisk;
  if(candidate==0 || (buy?trail>candidate:trail<candidate)) { candidate=trail; proposed=true; }
 }
 if(!proposed) return 0;
 candidate=NormalizeDouble((buy?MathFloor(candidate/tick+1e-8):MathCeil(candidate/tick-1e-8))*tick,_Digits);
 if(candidate<=0 || (currentSL>0 && (buy?candidate<=currentSL+tick*0.1:candidate>=currentSL-tick*0.1))) return 0;
 if(buy?price-candidate<minimumGap:candidate-price<minimumGap) return 0;
 return candidate;
}
void ManageOpenPositions()
{
 if(!MoveToBreakEvenAt1R && !EnableRRTrail) return;
 for(int i=PositionsTotal()-1;i>=0;i--)
 {
  ulong ticket=PositionGetTicket(i);
  if(!PositionSelectByTicket(ticket) || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=MagicNumber) continue;
  bool buy=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;
  double entry=PositionGetDouble(POSITION_PRICE_OPEN),sl=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP);
  ulong identifier=(ulong)PositionGetInteger(POSITION_IDENTIFIER);
  double risk=InitialPositionRisk(identifier,entry,buy); if(risk<=0) continue;
  MqlTick quote={}; if(!SymbolInfoTick(_Symbol,quote)) continue;
  double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE),price=buy?quote.bid:quote.ask;
  double gap=MathMax((double)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL),(double)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_FREEZE_LEVEL))*_Point+tick;
  double candidate=ManagedStop(buy,entry,sl,risk,price,tick,gap,MoveToBreakEvenAt1R,BreakEvenBufferPoints,EnableRRTrail,TrailStartRR,TrailDistanceRR);
  if(candidate<=0) continue;
  MqlTradeRequest request={}; MqlTradeResult result={};
  request.action=TRADE_ACTION_SLTP; request.position=ticket; request.symbol=_Symbol; request.magic=MagicNumber;
  request.sl=candidate; request.tp=tp;
  if(OrderSend(request,result) && (result.retcode==TRADE_RETCODE_DONE || result.retcode==TRADE_RETCODE_NO_CHANGES))
  { if(result.retcode==TRADE_RETCODE_DONE) Log("Break-even/trailing SL -> "+DoubleToString(candidate,_Digits)); }
  else Log("Stop update deferred: "+IntegerToString((int)result.retcode)+" "+result.comment);
 }
}

void DrawTrendline(string name,const Swing &a,const Swing &b,color clr,int width)
  {
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_TREND,0,a.time,a.price,b.time,b.price);
   else { ObjectMove(0,name,0,a.time,a.price); ObjectMove(0,name,1,b.time,b.price); }
   ObjectSetInteger(0,name,OBJPROP_COLOR,clr); ObjectSetInteger(0,name,OBJPROP_WIDTH,width);
   ObjectSetInteger(0,name,OBJPROP_RAY_RIGHT,true); ObjectSetInteger(0,name,OBJPROP_STYLE,STYLE_SOLID);
  }
void DrawWickSwings(string prefix,Swing &highs[],Swing &lows[],int visibleCount)
  {
   ObjectsDeleteAll(0,prefix);
   int nh=ArraySize(highs),nl=ArraySize(lows);
   for(int i=MathMax(0,nh-visibleCount);i<nh;i++)
     {
      string n=prefix+"H_"+IntegerToString(i),label=(i>0 ? (highs[i].price>highs[i-1].price?"HH":"LH") : "H");
      ObjectCreate(0,n,OBJ_ARROW,0,highs[i].time,highs[i].price); ObjectSetInteger(0,n,OBJPROP_ARROWCODE,217); ObjectSetInteger(0,n,OBJPROP_COLOR,clrSilver);
      ObjectCreate(0,n+"_T",OBJ_TEXT,0,highs[i].time,highs[i].price); ObjectSetString(0,n+"_T",OBJPROP_TEXT,label); ObjectSetInteger(0,n+"_T",OBJPROP_COLOR,clrSilver); ObjectSetInteger(0,n+"_T",OBJPROP_ANCHOR,ANCHOR_LEFT_LOWER);
     }
   for(int i=MathMax(0,nl-visibleCount);i<nl;i++)
     {
      string n=prefix+"L_"+IntegerToString(i),label=(i>0 ? (lows[i].price>lows[i-1].price?"HL":"LL") : "L");
      ObjectCreate(0,n,OBJ_ARROW,0,lows[i].time,lows[i].price); ObjectSetInteger(0,n,OBJPROP_ARROWCODE,218); ObjectSetInteger(0,n,OBJPROP_COLOR,clrWhite);
      ObjectCreate(0,n+"_T",OBJ_TEXT,0,lows[i].time,lows[i].price); ObjectSetString(0,n+"_T",OBJPROP_TEXT,label); ObjectSetInteger(0,n+"_T",OBJPROP_COLOR,clrWhite); ObjectSetInteger(0,n+"_T",OBJPROP_ANCHOR,ANCHOR_LEFT_UPPER);
     }
  }
void DrawSRZone(string name,datetime start,double level,color clr)
  {
   double w=SRZoneWidthPoints*Pt(); datetime end=TimeCurrent()+PeriodSeconds(Period())*20;
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_RECTANGLE,0,start,level+w,end,level-w);
   else { ObjectMove(0,name,0,start,level+w); ObjectMove(0,name,1,end,level-w); }
   ObjectSetInteger(0,name,OBJPROP_COLOR,clr); ObjectSetInteger(0,name,OBJPROP_WIDTH,2); ObjectSetInteger(0,name,OBJPROP_FILL,false);
   ObjectSetInteger(0,name,OBJPROP_BACK,false); ObjectSetInteger(0,name,OBJPROP_STYLE,STYLE_SOLID);
   string label=name+"_Label";
   if(ObjectFind(0,label)<0) ObjectCreate(0,label,OBJ_TEXT,0,start,level+w);
   else ObjectMove(0,label,0,start,level+w);
   ObjectSetString(0,label,OBJPROP_TEXT,(StringFind(name,"Resistance")>=0?"KEY RESISTANCE":"KEY SUPPORT"));
   ObjectSetInteger(0,label,OBJPROP_COLOR,clr); ObjectSetInteger(0,label,OBJPROP_FONTSIZE,8); ObjectSetInteger(0,label,OBJPROP_ANCHOR,ANCHOR_LEFT_LOWER);
  }
bool FindTrendlineAnchors(Direction direction,Swing &highs[],Swing &lows[],Swing &a,Swing &b)
  {
   // Uptrend: connect the last two confirmed higher-low wicks. Downtrend: last two lower-high wicks.
   if(direction==DIR_BUY)
     {
      int n=ArraySize(lows); for(int i=n-1;i>=1;i--) if(lows[i].price>lows[i-1].price) { a=lows[i-1]; b=lows[i]; return true; }
     }
   if(direction==DIR_SELL)
     {
      int n=ArraySize(highs); for(int i=n-1;i>=1;i--) if(highs[i].price<highs[i-1].price) { a=highs[i-1]; b=highs[i]; return true; }
     }
   return false;
  }
void DrawStructure()
  {
   if(!EnableChartObjects) return;
   // Never overlay all M15 fractals on an H4 chart. It is visual noise, not confluence.
   DrawWickSwings("BR_H4_",g_h4Highs,g_h4Lows,4);
   bool onM15=(Period()==PERIOD_M15);
   if(onM15) DrawWickSwings("BR_M15_",g_m15Highs,g_m15Lows,4);
   else ObjectsDeleteAll(0,"BR_M15_");
   int nh=ArraySize(g_h4Highs),nl=ArraySize(g_h4Lows);
   Swing a,b;
   if(FindTrendlineAnchors(g_h4Bias,g_h4Highs,g_h4Lows,a,b)) DrawTrendline("BR_H4_Trendline",a,b,clrBlack,2);
   else ObjectDelete(0,"BR_H4_Trendline");
   // These are the protected H4 wick levels that matter to a reversal—not arbitrary recent fractals.
   if(nh>0) DrawSRZone("BR_H4_Resistance",g_h4Highs[nh-1].time,g_h4Highs[nh-1].price,clrBlack);
   if(nl>0) DrawSRZone("BR_H4_Support",g_h4Lows[nl-1].time,g_h4Lows[nl-1].price,clrBlack);
   if(!onM15) { ObjectDelete(0,"BR_M15_Trendline"); ObjectDelete(0,"BR_M15_RetestLevel"); ObjectDelete(0,"BR_M15_SRZone"); return; }
   nh=ArraySize(g_m15Highs); nl=ArraySize(g_m15Lows);
   if(g_h4Bias==DIR_BUY && nh>=2) DrawTrendline("BR_M15_Trendline",g_m15Highs[nh-2],g_m15Highs[nh-1],C'160,160,160',1);
   else if(g_h4Bias==DIR_SELL && nl>=2) DrawTrendline("BR_M15_Trendline",g_m15Lows[nl-2],g_m15Lows[nl-1],C'160,160,160',1);
   else ObjectDelete(0,"BR_M15_Trendline");
   if(g_waitingRetest)
     {
      datetime t1=g_breakTime,t2=TimeCurrent()+PeriodSeconds(EXEC_TF)*12;
      if(ObjectFind(0,"BR_M15_RetestLevel")<0) ObjectCreate(0,"BR_M15_RetestLevel",OBJ_TREND,0,t1,g_breakLevel,t2,g_breakLevel);
      else { ObjectMove(0,"BR_M15_RetestLevel",0,t1,g_breakLevel); ObjectMove(0,"BR_M15_RetestLevel",1,t2,g_breakLevel); }
      ObjectSetInteger(0,"BR_M15_RetestLevel",OBJPROP_COLOR,clrWhite); ObjectSetInteger(0,"BR_M15_RetestLevel",OBJPROP_STYLE,STYLE_DASH); ObjectSetInteger(0,"BR_M15_RetestLevel",OBJPROP_WIDTH,2);
      datetime z1=g_breakTime,z2=TimeCurrent()+PeriodSeconds(EXEC_TF)*12; double w=SRZoneWidthPoints*Pt();
      if(ObjectFind(0,"BR_M15_SRZone")<0) ObjectCreate(0,"BR_M15_SRZone",OBJ_RECTANGLE,0,z1,g_breakLevel+w,z2,g_breakLevel-w);
      else { ObjectMove(0,"BR_M15_SRZone",0,z1,g_breakLevel+w); ObjectMove(0,"BR_M15_SRZone",1,z2,g_breakLevel-w); }
      ObjectSetInteger(0,"BR_M15_SRZone",OBJPROP_COLOR,C'90,90,90'); ObjectSetInteger(0,"BR_M15_SRZone",OBJPROP_FILL,true); ObjectSetInteger(0,"BR_M15_SRZone",OBJPROP_BACK,true);
     }
   else { ObjectDelete(0,"BR_M15_RetestLevel"); ObjectDelete(0,"BR_M15_SRZone"); }
  }
#include "BlackRockDisplay.mqh"
bool NewBar(ENUM_TIMEFRAMES tf,datetime &last) { datetime now=iTime(_Symbol,tf,0); if(now!=last) { last=now; return true; } return false; }
void UpdateH4()
  {
   Direction old=g_h4Bias; CollectSwings(BIAS_TF,H4SwingStrength,g_h4Highs,g_h4Lows); g_h4Bias=ReadStructure(BIAS_TF,g_h4Highs,g_h4Lows,g_h4Bias);
   if(old!=g_h4Bias) { Log("H4 bias: "+DirText(old)+" -> "+DirText(g_h4Bias)); if(AlertOnBiasChange) Notify("H4 bias",DirText(g_h4Bias)); }
   DrawStructure(); ObjectsDeleteAll(0,"DB_UI_"); ObjectDelete(0,"DB_Toggle"); UpdatePanel();
  }
void UpdateM15()
  {
   Direction old=g_m15Bias; CollectSwings(EXEC_TF,M15SwingStrength,g_m15Highs,g_m15Lows); g_m15Bias=ReadStructure(EXEC_TF,g_m15Highs,g_m15Lows,g_m15Bias);
   if(old!=g_m15Bias) { Log("M15 bias: "+DirText(old)+" -> "+DirText(g_m15Bias)); if(AlertOnBiasChange) Notify("M15 bias",DirText(g_m15Bias)); }
   ProcessReversal(old);
   DrawStructure(); ObjectsDeleteAll(0,"DB_UI_"); ObjectDelete(0,"DB_Toggle"); UpdatePanel();
  }
int OnInit()
  {
   if(RiskPercent<=0 || RiskPercent>100 || TargetRR<=0 || H4SwingStrength<1 || M15SwingStrength<1 || StructureLookbackBars<10 || StopBufferPoints<0 || TrailStartRR<=0 || TrailDistanceRR<=0 || BreakEvenBufferPoints<0) return INIT_PARAMETERS_INCORRECT;
   g_runtimeEntries=EnableAutomatedEntries;
   SaveTheme(); ApplyTheme(); DrawWallpaper();
   g_lastH4Bar=iTime(_Symbol,BIAS_TF,0); g_lastM15Bar=iTime(_Symbol,EXEC_TF,0);
   UpdateH4(); UpdateM15(); UpdatePanel(); EventSetTimer(1);
   Log("Black Rock 2.00: installed Human Apostle mapping / confirmed zone execution");
   return INIT_SUCCEEDED;
  }
void OnDeinit(const int reason)
  { EventKillTimer(); ObjectsDeleteAll(0,"BR_"); ObjectsDeleteAll(0,"BlackRock_"); ObjectsDeleteAll(0,"DB_"); ResourceFree(g_background); RestoreTheme(); }
void OnTick()
  { ManageOpenPositions(); if(NewBar(BIAS_TF,g_lastH4Bar)) UpdateH4(); if(NewBar(EXEC_TF,g_lastM15Bar)) UpdateM15(); ExecuteRetest(); UpdatePanel(); }