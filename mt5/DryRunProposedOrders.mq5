// Read Python proposed orders and log what MT5 would do.
//
// This Expert Advisor does not place, modify, or close trades. It only reads
// syphonix_proposed_orders.csv from MQL5/Files and prints dry-run actions.

#property strict

input string ProposedOrdersFile = "syphonix_proposed_orders.csv";
input int TimerSeconds = 10;

string LastFingerprint = "";

string Upper(string value)
{
   string result = value;
   StringToUpper(result);
   return result;
}

int OnInit()
{
   EventSetTimer(TimerSeconds);
   CheckProposedOrders();
   Print("DryRunProposedOrders: started; reading ", ProposedOrdersFile);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("DryRunProposedOrders: stopped");
}

void OnTimer()
{
   CheckProposedOrders();
}

void CheckProposedOrders()
{
   if(!FileIsExist(ProposedOrdersFile))
   {
      return;
   }

   int handle = FileOpen(ProposedOrdersFile, FILE_READ | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("DryRunProposedOrders: FileOpen failed for ", ProposedOrdersFile, " error=", GetLastError());
      return;
   }

   // Header: timestamp,symbol,side,volume_lots,order_type,dry_run,reason
   string header = "";
   for(int i = 0; i < 7 && !FileIsEnding(handle); i++)
   {
      header += FileReadString(handle);
      if(i < 6)
      {
         header += "|";
      }
   }

   string fingerprint = "";
   int orderCount = 0;
   string messages[];

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
      string dryRun = FileReadString(handle);
      string reason = FileReadString(handle);

      string message = "WOULD " + Upper(side) + " " + symbol + " " + volume
         + " lots (" + orderType + ", dry_run=" + dryRun + ") reason=" + reason;
      fingerprint += timestamp + "|" + symbol + "|" + side + "|" + volume + ";";
      ArrayResize(messages, orderCount + 1);
      messages[orderCount] = message;
      orderCount++;
   }

   FileClose(handle);

   if(fingerprint == LastFingerprint)
   {
      return;
   }
   LastFingerprint = fingerprint;

   if(orderCount == 0)
   {
      Print("DryRunProposedOrders: ACTION HOLD - no proposed orders");
      return;
   }

   Print("DryRunProposedOrders: ", orderCount, " proposed dry-run orders");
   for(int j = 0; j < orderCount; j++)
   {
      Print("DryRunProposedOrders: ", messages[j]);
   }
}
