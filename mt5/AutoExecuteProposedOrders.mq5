// Execute Python proposed orders with hard safety rails.
//
// This EA reads syphonix_proposed_orders.csv from MQL5/Files. It defaults to
// dry-run mode. Live execution requires all three gates:
// 1. DryRunMode = false in EA inputs
// 2. ArmedForLiveTrading = true in EA inputs
// 3. CSV row dry_run column = false
//
// Safety behavior:
// - Ignores the existing file when attached, so old orders do not fire.
// - Executes only when the proposed-order file fingerprint changes.
// - Caps each order to MaxOrderLots.
// - Rejects stale signal timestamps.
// - Only trades AllowedSymbols.

#property strict

#include <Trade/Trade.mqh>

input string ProposedOrdersFile = "syphonix_proposed_orders.csv";
input int TimerSeconds = 5;
input bool DryRunMode = true;
input bool ArmedForLiveTrading = false;
input double MaxOrderLots = 0.10;
input int MaxSignalAgeMinutes = 30;
input int DeviationPoints = 20;
input long MagicNumber = 26062201;
input string AllowedSymbols = "AUDUSD,EURCHF,EURGBP,EURUSD,GBPUSD,USDCAD,USDCHF,USDJPY,XAGUSD,XAUUSD";
input bool ProtectOpenPositions = true;
input bool ProtectOnlyMagicNumber = false;
input double DefaultStopLossUsd = 1500.0;
input double DefaultTakeProfitUsd = 3000.0;

CTrade Trade;
string LastFingerprint = "";

string Trim(string value)
{
   string result = value;
   StringTrimLeft(result);
   StringTrimRight(result);
   return result;
}

string UpperTrim(string value)
{
   string result = Trim(value);
   StringToUpper(result);
   return result;
}

bool CsvBool(string value)
{
   string normalized = UpperTrim(value);
   return normalized == "TRUE" || normalized == "1" || normalized == "YES";
}

bool ExtractTaggedDouble(string text, string tag, double &value)
{
   int start = StringFind(text, tag);
   if(start < 0)
   {
      return false;
   }

   start += StringLen(tag);
   int end = StringFind(text, ";", start);
   string raw;
   if(end < 0)
   {
      raw = StringSubstr(text, start);
   }
   else
   {
      raw = StringSubstr(text, start, end - start);
   }
   raw = Trim(raw);
   if(raw == "")
   {
      return false;
   }

   value = StringToDouble(raw);
   return value > 0.0;
}

bool IsAllowedSymbol(string symbol)
{
   string normalizedSymbol = UpperTrim(symbol);
   string allowedSymbols = AllowedSymbols;
   StringToUpper(allowedSymbols);
   string allowed = "," + allowedSymbols + ",";
   StringReplace(allowed, " ", "");
   return StringFind(allowed, "," + normalizedSymbol + ",") >= 0;
}

datetime ParseIsoTimestamp(string timestamp)
{
   string value = Trim(timestamp);
   if(StringLen(value) >= 19)
   {
      value = StringSubstr(value, 0, 19);
   }
   StringReplace(value, "T", " ");
   StringReplace(value, "-", ".");
   return StringToTime(value);
}

bool IsFreshSignal(string timestamp)
{
   datetime signalTime = ParseIsoTimestamp(timestamp);
   if(signalTime <= 0)
   {
      Print("AutoExecuteProposedOrders: blocked row with unparseable timestamp=", timestamp);
      return false;
   }

   int ageSeconds = (int)(TimeCurrent() - signalTime);
   if(ageSeconds < 0)
   {
      ageSeconds = 0;
   }
   if(ageSeconds > MaxSignalAgeMinutes * 60)
   {
      Print("AutoExecuteProposedOrders: blocked stale row timestamp=", timestamp,
         " age_seconds=", ageSeconds);
      return false;
   }
   return true;
}

void NormalizeProtection(string symbol, double &stopLoss, double &takeProfit)
{
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   if(stopLoss > 0.0)
   {
      stopLoss = NormalizeDouble(stopLoss, digits);
   }
   if(takeProfit > 0.0)
   {
      takeProfit = NormalizeDouble(takeProfit, digits);
   }
}

void ClampProtectionToBrokerRules(string symbol, bool isBuy, double &stopLoss, double &takeProfit)
{
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   int stopsLevel = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double minDistance = MathMax(point, stopsLevel * point);
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);

   if(point <= 0.0 || bid <= 0.0 || ask <= 0.0)
   {
      return;
   }

   if(isBuy)
   {
      if(stopLoss > 0.0)
      {
         stopLoss = MathMin(stopLoss, bid - minDistance);
      }
      if(takeProfit > 0.0)
      {
         takeProfit = MathMax(takeProfit, ask + minDistance);
      }
   }
   else
   {
      if(stopLoss > 0.0)
      {
         stopLoss = MathMax(stopLoss, ask + minDistance);
      }
      if(takeProfit > 0.0)
      {
         takeProfit = MathMin(takeProfit, bid - minDistance);
      }
   }
   NormalizeProtection(symbol, stopLoss, takeProfit);
}

bool DefaultProtectionForPosition(
   string symbol,
   ENUM_POSITION_TYPE positionType,
   double volume,
   double openPrice,
   double &stopLoss,
   double &takeProfit
)
{
   SymbolSelect(symbol, true);
   double tickSize = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tickSize <= 0.0 || tickValue <= 0.0 || volume <= 0.0 || openPrice <= 0.0)
   {
      Print("AutoExecuteProposedOrders: PROTECT SKIPPED ", symbol,
         " tick_size=", DoubleToString(tickSize, 10),
         " tick_value=", DoubleToString(tickValue, 10),
         " volume=", DoubleToString(volume, 2),
         " open_price=", DoubleToString(openPrice, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)));
      return false;
   }

   double usdPerPriceUnit = (tickValue / tickSize) * volume;
   if(usdPerPriceUnit <= 0.0)
   {
      Print("AutoExecuteProposedOrders: PROTECT SKIPPED ", symbol,
         " invalid usd_per_price_unit=", DoubleToString(usdPerPriceUnit, 10));
      return false;
   }

   double stopDistance = DefaultStopLossUsd / usdPerPriceUnit;
   double takeProfitDistance = DefaultTakeProfitUsd / usdPerPriceUnit;
   bool isBuy = positionType == POSITION_TYPE_BUY;
   if(isBuy)
   {
      stopLoss = openPrice - stopDistance;
      takeProfit = openPrice + takeProfitDistance;
   }
   else
   {
      stopLoss = openPrice + stopDistance;
      takeProfit = openPrice - takeProfitDistance;
   }
   ClampProtectionToBrokerRules(symbol, isBuy, stopLoss, takeProfit);
   if(stopLoss <= 0.0 || takeProfit <= 0.0)
   {
      Print("AutoExecuteProposedOrders: PROTECT SKIPPED ", symbol,
         " invalid computed sl=", DoubleToString(stopLoss, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)),
         " tp=", DoubleToString(takeProfit, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)));
      return false;
   }
   return stopLoss > 0.0 && takeProfit > 0.0;
}

void ProtectExistingPositions()
{
   if(!ProtectOpenPositions)
   {
      return;
   }

   Trade.SetExpertMagicNumber(MagicNumber);
   Trade.SetDeviationInPoints(DeviationPoints);

   int total = PositionsTotal();
   if(total <= 0)
   {
      return;
   }
   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
      {
         continue;
      }

      string symbol = UpperTrim(PositionGetString(POSITION_SYMBOL));
      if(!IsAllowedSymbol(symbol))
      {
         Print("AutoExecuteProposedOrders: PROTECT SKIPPED disallowed symbol=", symbol);
         continue;
      }

      long positionMagic = PositionGetInteger(POSITION_MAGIC);
      if(ProtectOnlyMagicNumber && positionMagic != MagicNumber)
      {
         continue;
      }

      ENUM_POSITION_TYPE positionType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double volume = PositionGetDouble(POSITION_VOLUME);
      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double currentStopLoss = PositionGetDouble(POSITION_SL);
      double currentTakeProfit = PositionGetDouble(POSITION_TP);

      double proposedStopLoss = 0.0;
      double proposedTakeProfit = 0.0;
      if(!DefaultProtectionForPosition(
         symbol,
         positionType,
         volume,
         openPrice,
         proposedStopLoss,
         proposedTakeProfit
      ))
      {
         continue;
      }

      bool isBuy = positionType == POSITION_TYPE_BUY;
      double finalStopLoss = currentStopLoss;
      double finalTakeProfit = currentTakeProfit;
      if(currentStopLoss <= 0.0
         || (isBuy && proposedStopLoss > currentStopLoss)
         || (!isBuy && proposedStopLoss < currentStopLoss))
      {
         finalStopLoss = proposedStopLoss;
      }
      if(currentTakeProfit <= 0.0)
      {
         finalTakeProfit = proposedTakeProfit;
      }

      if(finalStopLoss == currentStopLoss && finalTakeProfit == currentTakeProfit)
      {
         continue;
      }

      if(Trade.PositionModify(symbol, finalStopLoss, finalTakeProfit))
      {
         Print("AutoExecuteProposedOrders: PROTECTED ", symbol,
            " sl=", DoubleToString(finalStopLoss, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)),
            " tp=", DoubleToString(finalTakeProfit, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)));
      }
      else
      {
         Print("AutoExecuteProposedOrders: PROTECT FAILED ", symbol,
            " sl=", DoubleToString(finalStopLoss, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)),
            " tp=", DoubleToString(finalTakeProfit, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)),
            " retcode=", Trade.ResultRetcode(),
            " description=", Trade.ResultRetcodeDescription());
      }
   }
}

bool ReadOrders(string &fingerprint, string &rows[])
{
   fingerprint = "";
   ArrayResize(rows, 0);

   if(!FileIsExist(ProposedOrdersFile))
   {
      return false;
   }

   int handle = FileOpen(ProposedOrdersFile, FILE_READ | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("AutoExecuteProposedOrders: FileOpen failed for ", ProposedOrdersFile,
         " error=", GetLastError());
      return false;
   }

   // Header: timestamp,symbol,side,volume_lots,order_type,dry_run,reason
   for(int i = 0; i < 7 && !FileIsEnding(handle); i++)
   {
      FileReadString(handle);
   }

   int count = 0;
   while(!FileIsEnding(handle))
   {
      string timestamp = FileReadString(handle);
      if(timestamp == "")
      {
         break;
      }
      string symbol = FileReadString(handle);
      string side = FileReadString(handle);
      string volume = FileReadString(handle);
      string orderType = FileReadString(handle);
      string csvDryRun = FileReadString(handle);
      string reason = FileReadString(handle);

      string row = timestamp + "|" + symbol + "|" + side + "|" + volume + "|"
         + orderType + "|" + csvDryRun + "|" + reason;
      fingerprint += row + "\n";
      ArrayResize(rows, count + 1);
      rows[count] = row;
      count++;
   }

   FileClose(handle);
   return true;
}

void ExecuteRow(string row)
{
   string parts[];
   int partCount = StringSplit(row, '|', parts);
   if(partCount < 7)
   {
      Print("AutoExecuteProposedOrders: skipped malformed row=", row);
      return;
   }

   string timestamp = parts[0];
   string symbol = UpperTrim(parts[1]);
   string side = UpperTrim(parts[2]);
   double requestedLots = StringToDouble(parts[3]);
   string orderType = UpperTrim(parts[4]);
   bool csvDryRun = CsvBool(parts[5]);
   string reason = parts[6];
   double stopLoss = 0.0;
   double takeProfit = 0.0;
   ExtractTaggedDouble(reason, "sl_price=", stopLoss);
   ExtractTaggedDouble(reason, "tp_price=", takeProfit);

   if(orderType != "MARKET")
   {
      Print("AutoExecuteProposedOrders: blocked non-market order symbol=", symbol);
      return;
   }
   if(!IsAllowedSymbol(symbol))
   {
      Print("AutoExecuteProposedOrders: blocked disallowed symbol=", symbol);
      return;
   }
   if(!IsFreshSignal(timestamp))
   {
      return;
   }
   if(requestedLots <= 0.0)
   {
      Print("AutoExecuteProposedOrders: skipped non-positive volume symbol=", symbol);
      return;
   }

   double lots = MathMin(requestedLots, MaxOrderLots);
   lots = NormalizeDouble(lots, 2);
   if(lots <= 0.0)
   {
      Print("AutoExecuteProposedOrders: skipped after cap symbol=", symbol);
      return;
   }

   string action = side + " " + symbol + " " + DoubleToString(lots, 2)
      + " requested=" + DoubleToString(requestedLots, 2)
      + " sl=" + DoubleToString(stopLoss, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS))
      + " tp=" + DoubleToString(takeProfit, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS))
      + " reason=" + reason;

   if(DryRunMode || !ArmedForLiveTrading || csvDryRun)
   {
      Print("AutoExecuteProposedOrders: WOULD ", action,
         " gates dry_run_mode=", DryRunMode,
         " armed=", ArmedForLiveTrading,
         " csv_dry_run=", csvDryRun);
      return;
   }

   Trade.SetExpertMagicNumber(MagicNumber);
   Trade.SetDeviationInPoints(DeviationPoints);

   bool ok = false;
   if(side == "BUY")
   {
      ClampProtectionToBrokerRules(symbol, true, stopLoss, takeProfit);
      ok = Trade.Buy(lots, symbol, 0.0, stopLoss, takeProfit);
   }
   else if(side == "SELL")
   {
      ClampProtectionToBrokerRules(symbol, false, stopLoss, takeProfit);
      ok = Trade.Sell(lots, symbol, 0.0, stopLoss, takeProfit);
   }
   else
   {
      Print("AutoExecuteProposedOrders: blocked unknown side=", side);
      return;
   }

   if(ok)
   {
      Print("AutoExecuteProposedOrders: EXECUTED ", action);
   }
   else
   {
      Print("AutoExecuteProposedOrders: EXECUTE FAILED ", action,
         " retcode=", Trade.ResultRetcode(),
         " description=", Trade.ResultRetcodeDescription());
   }
}

void CheckProposedOrders(bool seedOnly)
{
   string fingerprint;
   string rows[];
   bool hasFile = ReadOrders(fingerprint, rows);
   if(!hasFile)
   {
      return;
   }

   if(seedOnly)
   {
      LastFingerprint = fingerprint;
      Print("AutoExecuteProposedOrders: seeded current file; waiting for next generated file");
      return;
   }

   if(fingerprint == LastFingerprint)
   {
      return;
   }
   LastFingerprint = fingerprint;

   int orderCount = ArraySize(rows);
   if(orderCount == 0)
   {
      Print("AutoExecuteProposedOrders: ACTION HOLD - no proposed orders");
      return;
   }

   Print("AutoExecuteProposedOrders: new proposed file with ", orderCount, " orders");
   for(int i = 0; i < orderCount; i++)
   {
      ExecuteRow(rows[i]);
   }
}

int OnInit()
{
   EventSetTimer(TimerSeconds);
   CheckProposedOrders(true);
   ProtectExistingPositions();
   Print("AutoExecuteProposedOrders: started; file=", ProposedOrdersFile,
      " dry_run_mode=", DryRunMode,
      " armed=", ArmedForLiveTrading,
      " max_order_lots=", DoubleToString(MaxOrderLots, 2),
      " protect_open_positions=", ProtectOpenPositions);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("AutoExecuteProposedOrders: stopped");
}

void OnTimer()
{
   CheckProposedOrders(false);
   ProtectExistingPositions();
}
