from AlgorithmImports import *
from EqualPCM import EqualWeightedPairsTradingPortfolio
from PairsTradingAlpha import PairsTradingAlphaModel
from ExecutionModel import MarketOrderModel
from RiskModel import NoRiskManagment
from datetime import timedelta
from System.Drawing import Color

### <summary>
### Framework algorithm that uses the PearsonCorrelationPairsTradingAlphaModel.
### This model extendes BasePairsTradingAlphaModel and uses Pearson correlation
### to rank the pairs trading candidates and use the best candidate to trade.
### </summary>
class PairsTradingV2(QCAlgorithm):
    '''Framework algorithm that uses the PearsonCorrelationPairsTradingAlphaModel.
    This model extendes BasePairsTradingAlphaModel and uses Pearson correlation
    to rank the pairs trading candidates and use the best candidate to trade.'''

    def Initialize(self):
        self.Debug('Algorithm started. Wait for warmup')
        self.SetStartDate(2015, 4, 1)
        self.SetEndDate(2016, 1, 1)
        self.SetWarmup(100)

        self.num_coarse = 20

        self.UniverseSettings.Resolution = Resolution.Hour

        self.AddUniverse(self.CoarseUniverse)
        self.SetAlpha(PairsTradingAlphaModel(coint_lookback = 200,
                                            coint_resolution = Resolution.Hour,
                                            prediction = timedelta(days=10),
                                            minimumCointegration = 0.05,
                                            std=2,
                                            stoplossStd=2.5,
                                            pairs_lookback=500,
                                            pairs_resolution=Resolution.Hour
                                            ))
        self.SetPortfolioConstruction(EqualWeightedPairsTradingPortfolio())
        self.SetExecution(MarketOrderModel())
        self.SetRiskManagement(NoRiskManagment())

        self.lastMonth = -1

        """
        stockPlot = Chart('Spread')
        stockPlot.AddSeries(Series('Spread', SeriesType.Line, '$', Color.Red))
        stockPlot.AddSeries(Series('Upper threshold', SeriesType.Line, '$', Color.Blue))
        stockPlot.AddSeries(Series('Lower threshold', SeriesType.Line, '$', Color.White))
        stockPlot.AddSeries(Series('Mean', SeriesType.Line,'$', Color.Yellow))
        self.AddChart(stockPlot)
        """


    def CoarseUniverse(self, coarse):

        if self.Time.month == self.lastMonth:
            return Universe.Unchanged
        self.lastMonth = self.Time.month
        #Exclude stocks like BRKA that cost 500.000 dollars
        selected = sorted([x for x in coarse if x.HasFundamentalData and x.Price > 15 and x.Price < 4000], 
                        key = lambda x: x.DollarVolume, reverse = True)

        return [x.Symbol for x in selected[:self.num_coarse]]


    def OnEndOfDay(self):
        self.Plot("Positions", "Num", len([x.Symbol for x in self.Portfolio.Values if self.Portfolio[x.Symbol].Invested]))
        self.Plot(f"Margin", "Used", self.Portfolio.TotalMarginUsed)
        self.Plot(f"Margin", "Remaining", self.Portfolio.MarginRemaining)
        self.Plot(f"Cash", "Remaining", self.Portfolio.Cash)

