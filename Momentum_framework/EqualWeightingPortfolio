#region imports
from AlgorithmImports import *
#endregion
class EqualWeightingPortfolio(PortfolioConstructionModel):


    def __init__(self, rebalance = Resolution.Daily, portfolioBias = PortfolioBias.LongShort):

        self.portfolioBias = portfolioBias

        # If the argument is an instance of Resolution or Timedelta
        # Redefine rebalancingFunc
        rebalancingFunc = rebalance
        if isinstance(rebalance, int):
            rebalance = Extensions.ToTimeSpan(rebalance)
        if isinstance(rebalance, timedelta):
            rebalancingFunc = lambda dt: dt + rebalance
        if rebalancingFunc:
            self.SetRebalancingFunc(rebalancingFunc)
            

    def DetermineTargetPercent(self, activeInsights):

        result = {}
        
        if not (activeInsights and self.Algorithm.IsMarketOpen(activeInsights[0].Symbol)):
            return result  

        self.Algorithm.Log(f'{self.Algorithm.Time} :: {len(activeInsights)}')

        # give equal weighting to each security
        count = sum(x.Direction != InsightDirection.Flat and self.RespectPortfolioBias(x) for x in activeInsights)
        percent = 0 if count == 0 else 1.0 / count
        for insight in activeInsights:
            result[insight] = (insight.Direction if self.RespectPortfolioBias(insight) else InsightDirection.Flat) * percent
        return result

    def RespectPortfolioBias(self, insight):
        return self.portfolioBias == PortfolioBias.LongShort or insight.Direction == self.portfolioBias  

