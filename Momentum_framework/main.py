from AlgorithmImports import *
from datetime import timedelta, time, datetime
from MomentumAlphaModel import MomentumAlphaModel
from EqualWeightingPortfolio import EqualWeightingPortfolio
from RiskModelWithSpy import RiskModelWithSpy

class MomentumFrameworkAlgo(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2006, 1, 1)
        self.SetEndDate(2010, 1, 1)
        self.SetCash(100000)  # Set Strategy Cash
        self.UniverseSettings.Resolution = Resolution.Hour
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        seeder = FuncSecuritySeeder(self.GetLastKnownPrices)
        self.SetSecurityInitializer(lambda security: seeder.SeedSecurity(security))

        self.SetWarmup(timedelta(360))
        self.SetBenchmark('SPY')
        
        self.spy = self.AddEquity('SPY', Resolution.Hour)
        
        self.AddUniverse(self.CoarseUniverse)
        pcm = EqualWeightingPortfolio(Expiry.EndOfMonth)
        self.SetPortfolioConstruction(pcm)
        self.SetExecution(ImmediateExecutionModel())
        self.AddAlpha(MomentumAlphaModel(lookback=203, resolution=Resolution.Daily)) 
        self.AddRiskManagement(RiskModelWithSpy(self, self.spy, 200, Resolution.Daily))
        
        self.num_coarse = 45
        self.lastMonth = -1

    def CoarseUniverse(self, coarse):
        if self.Time.month == self.lastMonth: 
            return Universe.Unchanged
        self.lastMonth = self.Time.month
        
        selected = sorted([x for x in coarse if x.HasFundamentalData and x.Price > 10], key = lambda x: x.DollarVolume, reverse=True)
        
        return [x.Symbol for x in selected[:self.num_coarse]]

    def OnEndOfDay(self):
        self.Plot("Positions", "Num", len([x.Symbol for x in self.Portfolio.Values if self.Portfolio[x.Symbol].Invested]))
        self.Plot(f"Margin", "Used", self.Portfolio.TotalMarginUsed)
        self.Plot(f"Margin", "Remaning", self.Portfolio.MarginRemaining)
        self.Plot(f"Cash", "Remaining", self.Portfolio.Cash)
