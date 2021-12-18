from collections import deque
from AlgorithmImports import *
from datetime import timedelta, time
import pandas as pd
import numpy as np


class BollBands(QCAlgorithm):
    #initialize method
    def Initialize(self):
        self.SetStartDate(2010, 10, 7)
        self.SetEndDate(2011, 10, 7)# Set Start Date
        self.SetCash(100000)  # Set Strategy Cash
        self.SetBenchmark('SPY')
        self.UniverseSettings.Resolution = Resolution.Daily
        self.SetWarmUp(timedelta(days=7))

        self.SetExecution(ImmediateExecutionModel())
        self.AddUniverse(self.CoarseUniverse, self.FineUniverse)
        self.SetPortfolioConstruction(EqualWeightingPortfolioConstructionModel())
        self.AddAlpha(AlphaBollingerBands())

        #used for rebalancing, and to select how many stocks goes to the coarse and fine.
        self.lastMonth = -1
        self.coarse_filter = 100
        self.fine_filter = 10

        self.vol_history = 120

    #Plotting standard variables
    def OnEndOfDay(self):
        self.Plot("Positions", "Num", len([x.Symbol for x in self.Portfolio.Values if self.Portfolio[x.Symbol].Invested]))
        self.Plot(f"Margin", "Used", self.Portfolio.TotalMarginUsed)
        self.Plot(f"Margin", "Remaining", self.Portfolio.MarginRemaining)
        self.Plot(f"Cash", "Remaining", self.Portfolio.Cash)
        self.Plot(f"Symboler", "Symboler", len(antal_symboler))

    def CoarseUniverse(self, coarse):
        #Rebalance function, once a month
        if self.Time.month == self.lastMonth:
            return Universe.Unchanged
        self.lastMonth = self.Time.month

        #sorting by stocks over 10 bucks, and that has fundamental data
        selected = sorted([x for x in coarse if x.Price > 10 and x.HasFundamentalData], key = lambda x: x.DollarVolume, reverse=True)

        return [x.Symbol for x in selected[:self.coarse_filter]]

    def FineUniverse(self, fine):

        #make a list that only contains the symbols
        filtered_fine = [x.Symbol for x in fine]

        #implement the methods that is described 
        stocks_by_vol = self.SortVolatility(filtered_fine, 360, Resolution.Daily)

        stocks_by_vol_keys = self.get_keys(stocks_by_vol)

        return [x for x in filtered_fine if str(x) in stocks_by_vol_keys[:self.fine_filter]]


    def SortVolatility(self, filtered_fine, lenght, resolution):
        #method that calculates the volatility with standard deviation, and returns it as a dict 
        history = self.History(filtered_fine, lenght, resolution)
        prices = history.drop_duplicates().close.unstack(level =0)
        vol = np.std(prices)
        vol_to_dict = vol.to_dict()
        rangeret = sorted(vol_to_dict, key = vol_to_dict.get, reverse = True)
        return {symbol: rank for rank, symbol in enumerate(rangeret, 1)}

    def get_keys(self, dic):
        #Method to get the 
        historie = {key:dic.get(key, 0) for key in set(dic)}
        historie = sorted(historie.items(), key = lambda x: x[1], reverse = False)
    
        listoflist = []

        for tuple1 in historie:
            list1 = list(tuple1)
            i = list1.pop(0)
            listoflist.append(i)
        
        return listoflist


class AlphaBollingerBands(AlphaModel):
    def __init__(self, 
                period = 10, 
                deviation = 2, 
                movingAverageType = MovingAverageType.Exponential, 
                resolution = Resolution.Daily):
                    
        self.period = period
        self.deviation = deviation
        self.movingAverageType = movingAverageType
        self.resolution = resolution
        self.insightPeriode = Time.Multiply(Extensions.ToTimeSpan(resolution), period)
        self.symbolDataBySymbol = {}
        global antal_symboler
        antal_symboler = self.symbolDataBySymbol
        
        self.days = 10
    
    def Update(self, algorithm, data):
        
        if not self.days == 10:
            self.days += 1
            return []
        else:
            self.days = 0
            
        insights = []

        for symbol, symbolDataBySymbol in self.symbolDataBySymbol.items():

            direction = InsightDirection.Flat

            price = symbolDataBySymbol.Security.Price
            lower = symbolDataBySymbol.Bollinger.LowerBand.Current.Value
            upper = symbolDataBySymbol.Bollinger.UpperBand.Current.Value
            middle = symbolDataBySymbol.Bollinger.MiddleBand.Current.Value

            #implemeter "previous state" for at tjekke hvilken tilstand at den sidst var i
            if symbolDataBySymbol.Security.Invested:
                if algorithm.Portfolio[symbol.Symbol].IsLong:
                    if price >= middle:
                        direction = InsightDirection.Flat
                    else:
                        direction = InsightDirection.Up

                elif algorithm.Portfolio[symbol.Symbol].IsShort:
                    if price <= middle:
                        direction = InsightDirection.Flat
                    else:
                        direction = InsightDirection.Down

                    

            elif not symbolDataBySymbol.Security.Invested:
                if price <= lower:
                    direction = InsightDirection.Up
                elif price >= upper:
                    direction = InsightDirection.Down
                else:
                    direction = InsightDirection.Flat

            if direction == symbolDataBySymbol.PreviousDirection:
                continue

            insight = Insight.Price(symbolDataBySymbol.Security.Symbol, self.insightPeriode, direction)
            symbolDataBySymbol.PreviousDirections = insight.Direction
            insights.append(insight)
        
        return insights

    def OnSecuritiesChanged(self, algorithm, changes):

        for symbol in changes.AddedSecurities:
            if symbol not in self.symbolDataBySymbol:
                symbol_data = SymbolData(symbol)
                symbol_data.RegisterIndicatorBollinger(algorithm, self.period, self.deviation, self.movingAverageType, self.resolution)
                
                history = algorithm.History([symbol.Symbol], self.period, self.resolution)

                if not symbol_data.Bollinger.IsReady:
                    symbol_data.WarmUpIndicators(history, symbol)
                
                self.symbolDataBySymbol[symbol] = symbol_data

        
        for removed in changes.RemovedSecurities:
            data = self.symbolDataBySymbol.pop(removed)
            if data is not None:
                data.RemoveConsolidators(algorithm)

        

class SymbolData:


    def __init__(self, symbol):
        self.Security = symbol

    def RegisterIndicatorBollinger(self, algorithm, period, deviation, movingAverageType, resolution):
        self.period = period
        self.deviation = deviation
        self.movingAverageType = movingAverageType
        self.Consolidator = None
        self.Bollinger = BollingerBands(self.period, deviation, movingAverageType)
        self.Consolidator = algorithm.ResolveConsolidator(self.Security.Symbol, resolution)
        algorithm.RegisterIndicator(self.Security.Symbol, self.Bollinger, self.Consolidator)
        self.PreviousDirection = None

    def RemoveConsolidators(self, algorithm):
        if self.Consolidator is not None:
            algorithm.SubscriptionManager.RemoveConsolidator(self.Security.Symbol, self.Consolidator)

    def WarmUpIndicators(self, history, symbol):
        for time, row in history.loc[symbol.Symbol].iterrows():
            self.Bollinger.Update(time, row['close'])
