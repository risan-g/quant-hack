// Export completed M15 bars for the Syphonix manual-ticket bridge.
//
// This Expert Advisor does not place, modify, or close trades. It only writes a
// CSV file to the MetaTrader 5 Files directory.

#property strict

input string SymbolsCsv = "XAUUSD,USDJPY,USDCHF,AUDUSD,USDCAD";
input int BarsToExport = 96;
input string OutputFile = "syphonix_mt5_live_bars.csv";
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
   Print("ExportLiveBars: started; writing ", OutputFile);
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
