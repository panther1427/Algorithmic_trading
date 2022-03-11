#region imports
from AlgorithmImports import *
#endregion
class RiskModelWithSpy(RiskManagementModel):
    
    def __init__(self, algorithm, spy, lookback,  resolution):
        self.spy = spy
        
        self.lookback = lookback
        self.resolution = resolution
        
        self.symboldata = {}
        
        #Flag so we only instanciate it once
        self.symboldata[self.spy.Symbol] = EMASymbolData(algorithm, self.spy, self.lookback, self.resolution)
        
    def ManageRisk(self, algorithm, targets):
        
        targets = []
        
        for symbol, symboldata in self.symboldata.items():
            #logic. If price is below the current value for EMA, we send a portfoliotarget of 0
            spyValue = self.spy.Price
            AlmaValue = symboldata.EMA.Current.Value
            
            for kvp in algorithm.Securities:
                security = kvp.Value
                
                if spyValue <= AlmaValue:
                    targets.append(PortfolioTarget(security.Symbol, 0))
                    
        return targets

     
class EMASymbolData:
    
    def __init__(self, algorithm, security, lookback, resolution):
        symbol = security.Symbol
        self.Security = symbol
        self.Consolidator = algorithm.ResolveConsolidator(symbol, resolution)
        
        smaName = algorithm.CreateIndicatorName(symbol, f"SMA{lookback}", resolution)
        self.EMA = ExponentialMovingAverage(smaName, lookback)
        algorithm.RegisterIndicator(symbol, self.EMA, self.Consolidator)
        
        history = algorithm.History(symbol, lookback, resolution)
        if 'close' in history:
            history = history.close.unstack(0).squeeze()
            for time, value in history.iteritems():
                self.EMA.Update(time, value)
