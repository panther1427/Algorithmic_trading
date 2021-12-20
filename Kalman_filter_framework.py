from AlgorithmImports import *
from QuantConnect import Algorithm
import pandas as pd
from datetime import timedelta, time, datetime
import numpy as np
import statsmodels.api as sm
from pykalman import KalmanFilter
from collections import deque 

class CointegrationAndKalmanFilter(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2016, 4, 28)  # Set Start Date
        self.SetEndDate(2021, 5, 30)  # Set End Date
        self.SetCash(100000)  # Set Strategy Cash
        self.UniverseSettings.Resolution = Resolution.Daily
        self.SetBenchmark('SPY')
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)
        self.SetWarmup(timedelta(days = 7))
        
        self.AddUniverse(self.CoarseUniverse, self.FineUniverse)
        self.SetPortfolioConstruction(EqualWeightingPortfolioConstructionModel(rebalance = timedelta(weeks=1), portfolioBias = PortfolioBias.LongShort))
        self.SetExecution(ImmediateExecutionModel())
        self.AddAlpha(PairsTradingAlpha())
        
        self.num_coarse = 40
        #has to be a even number, or it wont be market neutral, or work at all
        self.lastMonth = -1
        
        self.resolution = Resolution.Daily
        self.lookback = timedelta(weeks=150)

    def OnEndOfDay(self):
        self.Plot("Positions", "Num", len([x.Symbol for x in self.Portfolio.Values if self.Portfolio[x.Symbol].Invested]))
        self.Plot(f"Margin", "Used", self.Portfolio.TotalMarginUsed)
        self.Plot(f"Margin", "Remaining", self.Portfolio.MarginRemaining)
        self.Plot(f"Cash", "Remaining", self.Portfolio.Cash)

        
    def CoarseUniverse(self, coarse):
        if self.Time.month == self.lastMonth:
            return Universe.Unchanged
        self.lastMonth = self.Time.month

        selected = sorted([x for x in coarse if x.HasFundamentalData and x.Price > 15], 
                        key = lambda x: x.DollarVolume, reverse = True)

        return [x.Symbol for x in selected[:self.num_coarse]]
    
    def FineUniverse(self, fine):
        filtered_fine = [x.Symbol for x in fine]
        
        history = self.make_and_unstack_dataframe(filtered_fine)

        global pvalue_matrix
        pvalue_matrix, pairs = self.find_cointegrated_pairs(history)
        
        #Aktier bliver appended hvis de er i vores filtered fine
        stocks = []
        for pair in pairs:
            stocks.append(pair[0])
            stocks.append(pair[1])
 
        #vælg de aktier som har en positiv zscore, aktierne ligger i pairs af hveranden
        final_stocks = [x for x in filtered_fine if str(x) in stocks]
        return final_stocks


    def make_and_unstack_dataframe(self, list1):
        dataframe = self.History(list1, self.lookback, self.resolution)
        dataframe = dataframe['close'].unstack(level=0)
        dataframe = dataframe.dropna(axis=1)
        return dataframe
        
        
    def find_cointegrated_pairs(self, dataframe, critical_level = 0.05):
        #method to calculate how cointegrated the stocks are
        n = dataframe.shape[1]
        pvalue_matrix = np.ones((n, n))
        keys = dataframe.columns 
        pairs = []
        #smart looping technique. Looks at every stocks and tests it cointegration. It is kind of slow though, could be improved. 
        for i in range(n):
            for ii in range(i+1, n): 
                stock1 = dataframe[keys[i]]
                stock2 = dataframe[keys[ii]]
                result = sm.tsa.stattools.coint(stock1, stock2) 
                pvalue = result[1] 
                pvalue_matrix[i, ii] = pvalue
                if pvalue < critical_level: 
                    pairs.append((keys[i], keys[ii], pvalue)) 

        return pvalue_matrix, pairs



class PairsTradingAlpha(AlphaModel):
    def __init__(self, resolution = Resolution.Daily, lookback = timedelta(weeks = 10), predictionInterval = timedelta(weeks=1)):
        #Vi sætter en lavere resolution, idet at vi ikke skal cointegrere, men beregne spread osv, hvor vi ikke har brug for så meget data
        self.resolution = resolution
        self.lookback = lookback
        self.predictionInterval = predictionInterval
        
        #Holder øje med de par vi har i vores algo
        self.pairs = dict()
        #Holder øje med alle symboler vi har i vores liste
        self.Securities = list()
        
    def Update(self, algorithm, data):
        
        insights =[]  

        for key, symbolData in self.pairs.items():
            
            df, stock_y, stock_x = self.PairsToListAndHistory(algorithm, symbolData.pair_symbol)
            
            spread, lower, middle, upper = self.setKalman(df, stock_y, stock_x)
            
            previous_state = symbolData.State
            
            
            #implement the trading logic. Also check if the stock is already invested
            
            stock_y_direction = InsightDirection.Flat
            stock_x_direction = InsightDirection.Flat
            
            #Hvis at spread er over std, så skal y stige, og x skal falde. Hvis spread er under std, skal y falde, og x stige
            
            ###Implementer State, og det skal gøres så når values kommer ind for første gang, får den en flat state

            if symbolData.IfInvested == 1:
                if previous_state == 1:
                    if spread <= middle:
                        stock_x_direction = InsightDirection.Flat
                        stock_y_direction = InsightDirection.Flat
                    #if spread dont go over middle, we do nothing
                    elif spread >= middle:
                        continue
                    
                if previous_state == -1:
                    if spread >= middle:
                        stock_x_direction = InsightDirection.Flat
                        stock_y_direction = InsightDirection.Flat
                    elif spread <= middle:
                        continue
            
            
            if symbolData.IfInvested == 0:
                if previous_state == 0:
                    if spread >= upper:
                        stock_y_direction = InsightDirection.Up
                        stock_x_direction = InsightDirection.Down
                    #sæt invested til 1, da vi har købt
                    elif spread <= lower:
                        stock_y_direction = InsightDirection.Down
                        stock_x_direction = InsightDirection.Up
                    #sæt invested til 1, da vi har købt
                else:
                    continue
                
                
                    
            if stock_x_direction and stock_y_direction == 0:
                symbolData.IfInvested = 0
                symbolData.State = 0
                
            elif stock_x_direction == -1 and stock_y_direction == 1:
                symbolData.IfInvested = 1
                symbolData.State = -1
                
            elif stock_x_direction == 1 and stock_y_direction == -1:
                symbolData.IfInvested = 1
                symbolData.State = 1
                
              
                    
            insight_y = Insight(stock_y, self.predictionInterval, InsightType.Price, stock_y_direction)
            insight_x = Insight(stock_x, self.predictionInterval, InsightType.Price, stock_x_direction)
            
            updated_dict = (stock_x, stock_y)
            symbolData.pair_symbol = updated_dict
            
            #brug extend og ikke append når vi skal tilføje en gruppe af insights
            if symbolData.State != previous_state:
                insights.extend(Insight.Group(insight_y, insight_x))
                algorithm.Log(f"Pairs of traded stocks is {stock_y} and {stock_x}, and the direction is {symbolData.State}")
            
        return insights
    
                
    def OnSecuritiesChanged(self, algorithm, changes):
        #adding securities to self.securities
        for security in changes.AddedSecurities:
            self.Securities.append(security)
            
        
        #logic for removing securities from self.securities
        for security in changes.RemovedSecurities:
            if security in self.Securities:
                self.Securities.remove(security)

        #Logic to remove securities from the self.pair
        for security in changes.RemovedSecurities:
            del_keys = []
            
            #måske brug den her logik? ### [k for k in self.pairs.keys() if security.Symbol in k] ###
            for key, symbolData, in self.pairs.items():
                if security in symbolData.pair_symbol:
                    del_keys.append(key)
 
            for key in del_keys:
                self.pairs.pop(key)
                
                
        self.UpdatePairs(algorithm)
        
        
    def UpdatePairs(self, algorithm):
        #bliver brugt til at updatere vores pairs, og at smide dem ind i listen
        symbols = [x.Symbol for x in self.Securities]
        
        for i in range(0, len(symbols)):
            asset_i = symbols[i]
            
            for ii in range(1+i, len(symbols)):
                asset_ii = symbols[ii]
                pair_symbol = (asset_i, asset_ii)
                
                if len(pair_symbol) != 2:
                    continue
                
                #hvis at vores pairs allerede er i eksisterende aktier, så går vi ud af funktionen
                if pair_symbol in self.pairs.values():
                    continue
                
                self.pairs[i] = symbolData(pair_symbol)

    def PairsToListAndHistory(self, algorithm, pair):
        #Virker som den skal. Funktion til at få historie
        stocks = list(pair)
        stock1 = stocks[0]
        stock2 = stocks[1]
        #dette parameter bruger vi, så vi kan finde ud af om vi allerede har investeret i disse to par. Vi sætter det til 0, da vi ikke har investeret endnu
        df1 = algorithm.History(stock1, self.lookback, self.resolution)
        df2 = algorithm.History(stock2, self.lookback, self.resolution)
        #smart løsning hvis 2 df skal sættes sammen korrekt i QC
        history = pd.concat([df1, df2], axis=0)
        history = history['close'].unstack(level=0)
        history = history.dropna(axis=1)
        return history, stock1, stock2


    
    def setKalman(self, df, stock1, stock2):
        x = df[stock1]
        y = df[stock2]
    
        df1 = pd.DataFrame({'y':y, 'x':x})
        df1.index = pd.to_datetime(df1.index)
    

        state_means = self.regression(self.avg(x), self.avg(y))
        df1['hr'] = - state_means[:, 0]
        df1['spread'] =  df1.y + (df1.x * df1.hr)
    
        dt = 1
        mu = np.average(df1.spread)
        theta = 1
    
        sigma = np.std(df1['spread'])
        ts = np.arange(0, len(df1['spread'].values), dt)
        var = np.array([sigma**2 / (2 * theta) * (1-np.exp(-2 * theta * t)) for t in ts])
        std = 2 * np.sqrt(var)
        std = std[-1]
        upper = mu + std
        lower = mu - std
        
        
        return df1.spread[-1], lower, mu, upper
        

    def avg(self, x):
        filter = KalmanFilter(transition_matrices = [1],
        observation_matrices = [1],
        initial_state_mean = 0,
        initial_state_covariance = 1,
        observation_covariance = 1,
        transition_covariance = .01)
        spread, _ = filter.filter(x.values)
        spread = pd.Series(spread.flatten(), index = x.index)
        return spread

    def regression(self, x ,y):
        x = self.avg(x)
        y = self.avg(y)
        filter = KalmanFilter(n_dim_obs = 1, 
        n_dim_state = 2, 
        initial_state_mean = [0,0], 
        initial_state_covariance = np.ones((2, 2)), 
        transition_matrices = np.eye(2), 
        observation_matrices = np.expand_dims(np.vstack([[x], [np.ones(len(x))]]).T, axis=1),
        observation_covariance = 2,
        transition_covariance = 1e-3 / (1 - 1e-3) * np.eye(2))
        spread, _ = filter.filter(y.values)
        return spread


class symbolData:
    
    def __init__(self, pair_symbol):
        self.pair_symbol = pair_symbol
        self.State = State.FlatRatio
        self.IfInvested = 0


class State(Enum):
    ShortRatio = -1
    FlatRatio = 0
    LongRatio = 1
