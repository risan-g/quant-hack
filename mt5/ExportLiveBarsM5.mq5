// Export completed M5 bars for Syphonix dry-run experiments.
//
// This Expert Advisor does not place, modify, or close trades. It writes a
// separate CSV so the live M15 bot remains untouched.

#property strict

input string SymbolsCsv = "AUDUSD,EURCHF,EURGBP,EURUSD,GBPUSD,USDCAD,USDCHF,USDJPY,XAGUSD,XAUUSD";
input int BarsToExport = 288;
input string OutputFile = "syphonix_mt5_live_bars_m5.csv";
input int TimerSeconds = 30;

string Symbols[];

int OnInit()
{
   int count = StringSplit(SymbolsCsv, ',', Symbols);
   if(count <= 0)
   {
      Print("ExportLiveBarsM5: no symbols configured");
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
   Print("ExportLiveBarsM5: started; writing ", OutputFile);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("ExportLiveBarsM5: stopped");
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
      Print("ExportLiveBarsM5: FileOpen failed for ", OutputFile, " error=", GetLastError());
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

      int copied = CopyRates(symbol, PERIOD_M5, 1, BarsToExport, rates);
      if(copied <= 0)
      {
         Print("ExportLiveBarsM5: CopyRates failed for ", symbol, " error=", GetLastError());
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
