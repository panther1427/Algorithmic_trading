from AlgorithmImports import *
from datetime import timedelta, time, datetime

from QuantConnect import Algorithm

class MomentumFrameworkAlgo(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2011, 1, 1)
        self.SetCash(100000)  # Set Strategy Cash
        self.UniverseSettings.Resolution = Resolution.Hour
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)
        self.SetWarmup(timedelta(360))
        self.SetBenchmark('SPY')
        
        
        self.spy = self.AddEquity('SPY')
        
        self.AddUniverse(self.CoarseUniverse)
        self.SetPortfolioConstruction(EqualWeightingPortfolioConstructionModel(rebalance = Expiry.EndOfMonth, portfolioBias = PortfolioBias.Long))
        self.SetExecution(ImmediateExecutionModel())
        self.AddAlpha(MomentumAlphaModel(lookback=420, resolution=Resolution.Daily)) 
        self.AddRiskManagement(RiskModelWithSpy(self.spy))
        
        self.num_coarse = 100 
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
    
class MomentumAlphaModel(AlphaModel):
    def __init__(self, lookback = 420, resolution = Resolution.Daily):
        self.lookback = lookback
        self.resolution = resolution
        self.predictionInterval = Expiry.EndOfMonth
        self.symbolDataBySymbol = {}
        
        self.num_insights = 10
        self.lastMonth = -1
        

    def Update(self, algorithm, data):
       
        if algorithm.Time.month == self.lastMonth:
            return []
        self.lastMonth = algorithm.Time.month
        
        insights = []

        for symbol, symbolData in self.symbolDataBySymbol.items():
            if symbolData.CanEmit:

                direction = InsightDirection.Flat
                magnitude = symbolData.Return
                if magnitude > 0: 
                    direction = InsightDirection.Up
                if magnitude < 0: 
                    continue

                insights.append(Insight.Price(symbol, self.predictionInterval, direction, magnitude, None))

        insights1 = sorted([x for x in insights], key = lambda x: x.Magnitude, reverse=True)
        
        return [x for x in insights1[:self.num_insights]]

    def OnSecuritiesChanged(self, algorithm, changes):
        
        # clean up data for removed securities
        for removed in changes.RemovedSecurities:
            symbolData = self.symbolDataBySymbol.pop(removed.Symbol, None)
            if symbolData is not None:
                symbolData.RemoveConsolidators(algorithm)

        # initialize data for added securities
        symbols = [ x.Symbol for x in changes.AddedSecurities ]
        history = algorithm.History(symbols, self.lookback, self.resolution)
        if history.empty: return

        tickers = history.index.levels[0]
        for ticker in tickers:
            symbol = SymbolCache.GetSymbol(ticker)

            if symbol not in self.symbolDataBySymbol:
                symbolData = SymbolData(symbol, self.lookback)
                self.symbolDataBySymbol[symbol] = symbolData
                symbolData.RegisterIndicators(algorithm, self.resolution)
                symbolData.WarmUpIndicators(history.loc[ticker])


        
class RiskModelWithSpy(RiskManagementModel):
    
    def __init__(self, spy, maximumDrawdown= 0.05, lookback = 200,  resolution = Resolution.Daily):
        self.spy = spy
        self.maximumDrawdown = -abs(maximumDrawdown)
        
        self.lookback = lookback
        self.resolution = resolution
        
        self.symboldata = {}
        
        #Flag so we only instanciate it once
        self.init = False
        
    def ManageRisk(self, algorithm, targets):
        
        targets = []
        
        if self.init == False:
            #Takes in spy, our lookback and resolution
            self.symboldata[self.spy.Symbol] = EMASymbolData(algorithm, self.spy, self.lookback, self.resolution)
            self.init = True
            
        
        for symbol, symboldata in self.symboldata.items():
            #logic. If price is below the current value for EMA, we send a portfoliotarget of 0
            spyValue = self.spy.Price
            AlmaValue = symboldata.EMA.Current.Value
            
            for kvp in algorithm.Securities:
                security = kvp.Value
                
                if not security.Invested:
                    continue
                
                if spyValue <= AlmaValue:
                    targets.append(PortfolioTarget(security.Symbol, 0))
                    
        return targets
        
        
        
class EMASymbolData:
    
    def __init__(self, algorithm, security, lookback, resolution):
        symbol = security.Symbol
        self.Security = symbol
        self.Consolidator = algorithm.ResolveConsolidator(symbol, resolution)
        
        smaName = algorithm.CreateIndicatorName(symbol, f"ALMA{lookback}", resolution)
        self.EMA = ExponentialMovingAverage(smaName, lookback)
        algorithm.RegisterIndicator(symbol, self.EMA, self.Consolidator)
        
        history = algorithm.History(symbol, lookback, resolution)
        if 'close' in history:
            history = history.close.unstack(0).squeeze()
            for time, value in history.iteritems():
                self.EMA.Update(time, value)
        


class SymbolData:

    def __init__(self, symbol, lookback):
        self.Symbol = symbol
        self.ROC = RateOfChange('{}.ROC({})'.format(symbol, lookback), lookback)
        self.Consolidator = None
        self.previous = 0

    def RegisterIndicators(self, algorithm, resolution):
        self.Consolidator = algorithm.ResolveConsolidator(self.Symbol, resolution)
        algorithm.RegisterIndicator(self.Symbol, self.ROC, self.Consolidator)

    def RemoveConsolidators(self, algorithm):
        if self.Consolidator is not None:
            algorithm.SubscriptionManager.RemoveConsolidator(self.Symbol, self.Consolidator)

    def WarmUpIndicators(self, history):
        for tuple in history.itertuples():
            self.ROC.Update(tuple.Index, tuple.close)

    @property
    def Return(self):
        return float(self.ROC.Current.Value)

    @property
    def CanEmit(self):
        if self.previous == self.ROC.Samples:
            return False

        self.previous = self.ROC.Samples
        return self.ROC.IsReady

    def __str__(self, **kwargs):
        return '{}: {:.2%}'.format(self.ROC.Name, (1 + self.Return)**252 - 1)
        
