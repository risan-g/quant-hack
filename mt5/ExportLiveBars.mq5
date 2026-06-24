// Export completed M15 bars for the Syphonix manual-ticket bridge.
//
// This Expert Advisor does not place, modify, or close trades. It only writes a
// CSV file to the MetaTrader 5 Files directory.

#property strict

input string SymbolsCsv = "AUDUSD,EURCHF,EURGBP,EURUSD,GBPUSD,USDCAD,USDCHF,USDJPY,XAGUSD";
input int BarsToExport = 96;
input string OutputFile = "syphonix_mt5_live_bars.csv";
input string PositionsOutputFile = "syphonix_mt5_positions.csv";
input int TimerSeconds = 30;

string Symbols[];

int OnInit()
{
   int count = StringSplit(SymbolsCsv, ',', Symbols);
   if(count <= 0)
   {
      Print("ExportLiveBars: no symbols configured");
      return INIT_FAILED;
   }

   for(int i = 0; i < count; i++)
   {
      StringTrimLeft(Symbols[i]);
      StringTrimRight(Symbols[i]);
      SymbolSelect(Symbols[i], true);
   }

   EventSetTimer(TimerSeconds);
   ExportBars();
   ExportPositions();
   Print("ExportLiveBars: started; writing ", OutputFile, " and ", PositionsOutputFile);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("ExportLiveBars: stopped");
}

void OnTimer()
{
   ExportBars();
   ExportPositions();
}

void ExportBars()
{
   int handle = FileOpen(OutputFile, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("ExportLiveBars: FileOpen failed for ", OutputFile, " error=", GetLastError());
      return;
   }

   FileWrite(
      handle,
      "exported_at",
      "symbol",
      "time",
      "bid_open",
      "bid_high",
      "bid_low",
      "bid_close",
      "current_bid",
      "current_ask",
      "tick_volume"
   );

   string exportedAt = TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS);

   for(int i = 0; i < ArraySize(Symbols); i++)
   {
      string symbol = Symbols[i];
      MqlRates rates[];
      ArraySetAsSeries(rates, true);

      int copied = CopyRates(symbol, PERIOD_M15, 1, BarsToExport, rates);
      if(copied <= 0)
      {
         Print("ExportLiveBars: CopyRates failed for ", symbol, " error=", GetLastError());
         continue;
      }

      MqlTick tick;
      bool hasTick = SymbolInfoTick(symbol, tick);
      double currentBid = hasTick ? tick.bid : 0.0;
      double currentAsk = hasTick ? tick.ask : 0.0;
      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);

      for(int j = copied - 1; j >= 0; j--)
      {
         FileWrite(
            handle,
            exportedAt,
            symbol,
            TimeToString(rates[j].time, TIME_DATE | TIME_SECONDS),
            DoubleToString(rates[j].open, digits),
            DoubleToString(rates[j].high, digits),
            DoubleToString(rates[j].low, digits),
            DoubleToString(rates[j].close, digits),
            DoubleToString(currentBid, digits),
            DoubleToString(currentAsk, digits),
            (long)rates[j].tick_volume
         );
      }
   }

   FileClose(handle);
}

void ExportPositions()
{
   int handle = FileOpen(PositionsOutputFile, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("ExportLiveBars: FileOpen failed for ", PositionsOutputFile, " error=", GetLastError());
      return;
   }

   FileWrite(
      handle,
      "exported_at",
      "balance",
      "equity",
      "margin",
      "free_margin",
      "margin_level",
      "symbol",
      "side",
      "volume",
      "price_open",
      "price_current",
      "profit"
   );

   string exportedAt = TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double margin = AccountInfoDouble(ACCOUNT_MARGIN);
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double marginLevel = AccountInfoDouble(ACCOUNT_MARGIN_LEVEL);
   int total = PositionsTotal();

   if(total == 0)
   {
      FileWrite(
         handle,
         exportedAt,
         DoubleToString(balance, 2),
         DoubleToString(equity, 2),
         DoubleToString(margin, 2),
         DoubleToString(freeMargin, 2),
         DoubleToString(marginLevel, 2),
         "",
         "flat",
         "0",
         "0",
         "0",
         "0"
      );
      FileClose(handle);
      return;
   }

   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
      {
         continue;
      }

      string symbol = PositionGetString(POSITION_SYMBOL);
      long type = PositionGetInteger(POSITION_TYPE);
      string side = type == POSITION_TYPE_BUY ? "buy" : "sell";
      double volume = PositionGetDouble(POSITION_VOLUME);
      double priceOpen = PositionGetDouble(POSITION_PRICE_OPEN);
      double priceCurrent = PositionGetDouble(POSITION_PRICE_CURRENT);
      double profit = PositionGetDouble(POSITION_PROFIT);
      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);

      FileWrite(
         handle,
         exportedAt,
         DoubleToString(balance, 2),
         DoubleToString(equity, 2),
         DoubleToString(margin, 2),
         DoubleToString(freeMargin, 2),
         DoubleToString(marginLevel, 2),
         symbol,
         side,
         DoubleToString(volume, 2),
         DoubleToString(priceOpen, digits),
         DoubleToString(priceCurrent, digits),
         DoubleToString(profit, 2)
      );
   }

   FileClose(handle);
}
