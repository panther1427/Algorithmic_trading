
from AlgorithmImports import *
import pandas as pd
import numpy as np
import statsmodels.api as sm
from enum import Enum
from collections import deque
from datetime import timedelta


class PairsTradingAlphaModel(AlphaModel):
    def __init__(self, coint_lookback, coint_resolution, prediction, minimumCointegration, std, stoplossStd, pairs_lookback, pairs_resolution):

        #We use these parameters to set the cointegration part of the algo
        self.coint_resolution = coint_resolution
        self.coint_lookback = coint_lookback
        self.minimumCointegration = minimumCointegration

        #here we set up the pairs trading lookback and resolution. This can and should be different than the coint
        self.pairs_lookback = pairs_lookback
        self.pairs_resolution = pairs_resolution

        self.prediction = prediction

        #Set the upper and lower standard deviation, that we want our algo to hit
        self.upperStd = std
        self.lowerStd = -abs(std)

        #This is the higher and lower stoploss of the algo
        self.upperStoploss = stoplossStd
        self.lowerStoploss = -abs(stoplossStd)
        self.mean = 0

        #We set the pairs (Used for the symbolData class) and securities, to keep track of the universe
        self.pairs = {}
        self.Securities = []


    def Update(self, algorithm, data):
        #implement the update features here. Update the RollingWindow
        insights = []

        #If the market is not open, we will not send out orders
        for symbol in self.Securities:
            if not algorithm.IsMarketOpen(symbol.Symbol):
                return []
        
        #update the rolling window with same slices, or ols wont fit
        for keys, symbolData in self.pairs.items():

            #if the window is varmed up and ready, we enter
            if symbolData.window1.IsReady and symbolData.window2.IsReady:
                
                #Get the state of the pairs
                state = symbolData.state

                #Convert the tradebar class to a pandas dataframe
                S1 = algorithm.PandasConverter.GetDataFrame[IBaseDataBar](symbolData.window1).close.unstack(level=0)
                S2 = algorithm.PandasConverter.GetDataFrame[IBaseDataBar](symbolData.window2).close.unstack(level=0)

                #Drop the data is there is nans
                S1 = S1.dropna(axis=1)
                S2 = S2.dropna(axis=1)
                
                #Add a constant, fit with regression(least ordinary squares) and get the parameteres
                S1 = sm.add_constant(S1)
                results = sm.OLS(S2, S1).fit()
                S1 = S1[keys[0]]
                S2 = S2[keys[1]]
                b = results.params[keys[0]]

                #If S2 moves higher, the spread becomes higher. Therefore, short S2, long S1 if spread moves up, mean reversion
                spread = S2 - b * S1

                #Get the zscore (the spread)
                zscore = self.ZScore(spread)

                insight, state = self.TradeLogic(keys[0], keys[1], zscore[-1], state)

                #self.Plotting(algorithm, zscore[-1], self.upperStd, self.lowerStd)

                #if we have changed state, append insight
                if symbolData.state != state:
                    insights.extend(insight)
                    symbolData.state = state
                else:
                    continue

        return insights

    """
    def Plotting(self, algorithm, spread, upper, lower):
        algorithm.Plot('Spread', 'Spread', spread)
        algorithm.Plot('Spread', 'Upper threshold', upper)
        algorithm.Plot('Spread', 'Lower threshold', lower)
        algorithm.Plot('Mean', 'Lower threshold', 0)
    """
    

    def TradeLogic(self, stock1, stock2, zscore, state):
        
        insights = []

        #If the state is flat, we look if the zscore is higher than 2 std up and down
        if state == State.FlatRatio:
            if zscore > self.upperStd:
                longS1 = Insight.Price(stock1, self.prediction, InsightDirection.Up, weight=1)
                shortS2 = Insight.Price(stock2, self.prediction, InsightDirection.Down, weight=-1)
                return Insight.Group(longS1, shortS2), State.LongRatio

            elif zscore < self.lowerStd:
                shortS1 = Insight.Price(stock1, self.prediction, InsightDirection.Down, weight=-1)
                longS2 = Insight.Price(stock2, self.prediction, InsightDirection.Up, weight=1)
                return Insight.Group(shortS1, longS2), State.ShortRatio

            else:
                return [], State.FlatRatio

        #if we are short, we look to close the trade, if it crosses the mean
        if state == State.ShortRatio:
            if zscore > self.mean:
                #liquidate
                flatS1 = Insight.Price(stock1, self.prediction, InsightDirection.Flat, weight=0)
                flatS2 = Insight.Price(stock2, self.prediction, InsightDirection.Flat, weight=0)
                return Insight.Group(flatS1, flatS2), State.FlatRatio

            elif zscore > self.lowerStoploss:
                #stop loss
                #when stop loss is trickered, we dont send the state to flat, as we will wait for the spread to cross below the mean, before doing that
                flatS1 = Insight.Price(stock1, self.prediction, InsightDirection.Flat, weight=0)
                flatS2 = Insight.Price(stock2, self.prediction, InsightDirection.Flat, weight=0)
                return Insight.Group(flatS1, flatS2), State.ShortRatio

            else:
                return [], State.ShortRatio

        #if we are long, we look to close the trade, if it crosses the mean
        if state == State.LongRatio:
            if zscore < self.mean:
                #liquidate
                flatS1 = Insight.Price(stock1, self.prediction, InsightDirection.Flat, weight=0)
                flatS2 = Insight.Price(stock2, self.prediction, InsightDirection.Flat, weight=0)
                return Insight.Group(flatS1, flatS2), State.FlatRatio

            elif zscore < self.lowerStoploss:
                #stop loss
                #when stop loss is trickered, we dont send the state to flat, as we will wait for the spread to cross below the mean, before doing that
                flatS1 = Insight.Price(stock1, self.prediction, InsightDirection.Flat, weight=0)
                flatS2 = Insight.Price(stock2, self.prediction, InsightDirection.Flat, weight=0)
                return Insight.Group(flatS1, flatS2), State.LongRatio

            else:
                return [], State.LongRatio
        
    def ZScore(self, series):
        #standardize the dataset
        return (series - series.mean()) / np.std(series)


    def OnSecuritiesChanged(self, algorithm, changes):
        
        #Add the added securites
        for security in changes.AddedSecurities:
            self.Securities.append(security)

        #Remove the removed securites
        for security in changes.RemovedSecurities:
            if security in self.Securities:
                self.Securities.remove(security)
        
        #Get the symbols of the equities
        symbols = [x.Symbol for x in self.Securities]

        #Get the history, only the close, and unstack the frame
        history = algorithm.History(symbols, self.coint_lookback, self.coint_resolution).close.unstack(level=0)

        #method to calculate how cointegrated the stocks are
        n = history.shape[1]
        keys = history.columns 

        #smart looping technique. Looks at every stocks and tests it cointegration.
        for i in range(n):
            for ii in range(i+1, n): 
                #Get the history of stock1 and 2
                stock1 = history[keys[i]]
                stock2 = history[keys[ii]]

                #Get the name of the stock 1 and 2
                asset1 = keys[i]
                asset2 = keys[ii]

                #Get the pairs, and the inverse
                pair_symbol = (asset1, asset2)
                invert = (asset2, asset1)

                #If we already have the pairs, we dont append
                if pair_symbol in self.pairs or invert in self.pairs:
                    continue
                
                #If there is nans in the frames, we continue (broken data)
                if stock1.hasnans or stock2.hasnans:
                    algorithm.Debug(f'WARNING! {asset1} and {asset2} has Nans. Did not perform coint')
                    continue

                #The cointegration part, that calculates cointegration between 2 stocks
                result = sm.tsa.stattools.coint(stock1, stock2) 
                pvalue = result[1] 
                if pvalue < self.minimumCointegration:
                    #We add the pairs to the symboldata, if coint is low
                    symbolData = AlphaSymbolData(algorithm, asset1, asset2, self.pairs_lookback)
                    self.pairs[pair_symbol] = symbolData
                    symbolData.RegisterIndicator(algorithm, self.pairs_resolution)

        for security in changes.RemovedSecurities:
            keys = [k for k in self.pairs.keys() if security.Symbol in k]

            #we remove from self.pairs, and from algorithm.SubscriptionsManager
            for key in keys:
                symbolData = self.pairs.pop(key)
                if symbolData is not None:
                    symbolData.RemoveConsolidator(algorithm)


class AlphaSymbolData:
    def __init__(self, algorithm, symbol1, symbol2, lookback):

        self.state = State.FlatRatio
        self.coint_lookback = lookback

        self.symbol1 = symbol1
        self.symbol2 = symbol2

        self.window1 = RollingWindow[TradeBar](lookback)
        self.window2 = RollingWindow[TradeBar](lookback)

        self.Consolidator1 = None
        self.Consolidator2 = None
        

    def RegisterIndicator(self, algorithm, resolution):
        self.Consolidator1 = TradeBarConsolidator(timedelta(hours=1))
        self.Consolidator2 = TradeBarConsolidator(timedelta(hours=1))

        self.Consolidator1.DataConsolidated += self.consolidation_handler1
        self.Consolidator2.DataConsolidated += self.consolidation_handler2

        algorithm.SubscriptionManager.AddConsolidator(self.symbol1, self.Consolidator1)
        algorithm.SubscriptionManager.AddConsolidator(self.symbol2, self.Consolidator2)


    def RemoveConsolidator(self, algorithm):
        if self.Consolidator1 is not None and self.Consolidator2 is not None:
            algorithm.SubscriptionManager.RemoveConsolidator(self.symbol1, self.Consolidator1)
            algorithm.SubscriptionManager.RemoveConsolidator(self.symbol2, self.Consolidator2)


    def consolidation_handler1(self, sender: object, consolidated_bar: TradeBar) -> None:
        self.window1.Add(consolidated_bar)


    def consolidation_handler2(self, sender: object, consolidated_bar: TradeBar) -> None:
        self.window2.Add(consolidated_bar)



class State(Enum):
    ShortRatio = -1
    FlatRatio = 0
    LongRatio = 1
