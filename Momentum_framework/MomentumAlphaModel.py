#region imports
from AlgorithmImports import *
#endregion
class MomentumAlphaModel(AlphaModel):
    def __init__(self, lookback, resolution):
        self.lookback = lookback
        self.resolution = resolution
        self.predictionInterval = Expiry.EndOfMonth
        self.symbolDataBySymbol = {}
        
        self.num_insights = 10
        self.lastMonth = -1
        

    def Update(self, algorithm, data):
        
        for symbol, symbolData in self.symbolDataBySymbol.items():
            if not algorithm.IsMarketOpen(symbol):
                return []

        if algorithm.Time.month == self.lastMonth:
            return []
        self.lastMonth = algorithm.Time.month
        
        insights = []

        for symbol, symbolData in self.symbolDataBySymbol.items():

            if symbolData.CanEmit:
                direction = InsightDirection.Up
                magnitude = symbolData.Return

                insights.append(Insight.Price(symbol, self.predictionInterval, direction, magnitude = magnitude))

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
            
            if symbol == "SPY":
                return

            if symbol not in self.symbolDataBySymbol:
                symbolData = SymbolData(symbol, self.lookback)
                self.symbolDataBySymbol[symbol] = symbolData
                symbolData.RegisterIndicators(algorithm, self.resolution)
                symbolData.WarmUpIndicators(history.loc[ticker])

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
