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
        #setting our start, end etc
        self.SetStartDate(2016, 4, 28)  # Set Start Date
        self.SetEndDate(2021, 12, 1)  # Set End Date
        self.SetCash(100000)  # Set Strategy Cash
        self.UniverseSettings.Resolution = Resolution.Daily
        self.SetBenchmark('SPY')
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)
        self.SetWarmup(timedelta(days = 7))
        
        #setting our universes and alphas etc
        self.AddUniverse(self.CoarseUniverse, self.FineUniverse)
        self.SetPortfolioConstruction(EqualWeightingPortfolioConstructionModel(rebalance = timedelta(weeks=1), portfolioBias = PortfolioBias.LongShort))
        self.SetExecution(ImmediateExecutionModel())
        self.AddAlpha(PairsTradingAlpha())
        
        #has to be a even number, or it wont be market neutral, or work at all
        self.num_coarse = 30
    
        #Used for rebalancing
        self.lastMonth = -1
        
        #our resolution and lookback for calculating the cointegration
        self.resolution = Resolution.Daily
        self.lookback = timedelta(weeks=150)

    def OnEndOfDay(self):
        #Used for plotting different things
        self.Plot("Positions", "Num", len([x.Symbol for x in self.Portfolio.Values if self.Portfolio[x.Symbol].Invested]))
        self.Plot(f"Margin", "Used", self.Portfolio.TotalMarginUsed)
        self.Plot(f"Margin", "Remaining", self.Portfolio.MarginRemaining)
        self.Plot(f"Cash", "Remaining", self.Portfolio.Cash)

        
    def CoarseUniverse(self, coarse):
        #Rebalance function, only rebalances our univers once pr month
        if self.Time.month == self.lastMonth:
            return Universe.Unchanged
        self.lastMonth = self.Time.month

        #selects stocks based on the stocks having fundamental data, and price over 15 dollars. Sorts it by volume
        selected = sorted([x for x in coarse if x.HasFundamentalData and x.Price > 15], 
                        key = lambda x: x.DollarVolume, reverse = True)

        return [x.Symbol for x in selected[:self.num_coarse]]
    
    def FineUniverse(self, fine):
        #returns only the tickers
        filtered_fine = [x.Symbol for x in fine]
        
        #Used to get our price history
        history = self.make_and_unstack_dataframe(filtered_fine)
        
        #retuns our matrix and the pairs
        pvalue_matrix, pairs = self.find_cointegrated_pairs(history)
        
        #appends the pairs to a list, so we get one long list
        stocks = []
        for pair in pairs:
            stocks.append(pair[0])
            stocks.append(pair[1])
            
 
        #makes a list and returns it, if the stock is in the filtered_fine list
        final_stocks = []
        
        for i in stocks:
            for ii in filtered_fine:
                if i == ii:
                    final_stocks.append(ii)
        
        return final_stocks


    def make_and_unstack_dataframe(self, list1):
        #makes and unstacks the dataframe
        dataframe = self.History(list1, self.lookback, self.resolution)
        dataframe = dataframe['close'].unstack(level=0)
        dataframe = dataframe.dropna(axis=1)
        return dataframe
        
        
    def find_cointegrated_pairs(self, dataframe, critical_level = 0.02):
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
                #The cointegration part, that calculates cointegration between 2 stocks
                result = sm.tsa.stattools.coint(stock1, stock2) 
                pvalue = result[1] 
                pvalue_matrix[i, ii] = pvalue
                if pvalue < critical_level: 
                    pairs.append((keys[i], keys[ii], pvalue)) 

        return pvalue_matrix, pairs



class PairsTradingAlpha(AlphaModel):
    def __init__(self, resolution = Resolution.Daily, lookback = timedelta(weeks = 5), predictionInterval = timedelta(weeks=1)):
        #setting our resolution lookback etc
        self.resolution = resolution
        self.lookback = lookback
        self.predictionInterval = predictionInterval
        
        #Keeps track of the pairs
        self.pairs = dict()
        #keeps track of all the stock, not listed by pairs
        self.Security = list()
        
    def Update(self, algorithm, data):
        
        #our insight list, which we will return when the looping  is done
        insights =[]  

        #loops through our dictionary
        for key, symbolData in self.pairs.items():
            
            #uses the function, and gives 3 paramteres
            df, stock_y, stock_x = self.PairsToListAndHistory(algorithm, symbolData.pair_symbol)
            
            #calculates the kalman filter, and calculates the spread
            spread, lower, middle, upper = self.setKalman(df, stock_y, stock_x)
            
            #Sets the prev state, to the state before the trading logic takes place
            previous_state = symbolData.State
            
            
            #sets the direction to flat
            stock_y_direction = InsightDirection.Flat
            stock_x_direction = InsightDirection.Flat
            
            #Hvis at spread er over std, så skal y stige, og x skal falde. Hvis spread er under std, skal y falde, og x stige
            
            
            #Our logic to make trades. If the pairs is already invested, we go into the loop
            if symbolData.IfInvested == 1:
                #If we have gone short on the spread, enter this logic
                if previous_state == 1:
                    #If the spread returns to mean, we liquidate
                    if spread <= middle:
                        stock_x_direction = InsightDirection.Flat
                        stock_y_direction = InsightDirection.Flat
                    #if spread dont go over middle, we do nothing
                    elif spread >= middle:
                        continue
                    
                #If we have gone short on the spread, enter this logic
                if previous_state == -1:
                    #If spread has returned to the mean
                    if spread >= middle:
                        stock_x_direction = InsightDirection.Flat
                        stock_y_direction = InsightDirection.Flat
                    #if spread dont go over middle, we do nothing
                    elif spread <= middle:
                        continue
            
            #If we have not invested in the spread, enter this logic
            if symbolData.IfInvested == 0:
                #If we have done nothing about the spread
                if previous_state == 0:
                    #If spread is over 2 std
                    if spread >= upper:
                        stock_y_direction = InsightDirection.Up
                        stock_x_direction = InsightDirection.Down
                    #If spread is under 2 std
                    elif spread <= lower:
                        stock_y_direction = InsightDirection.Down
                        stock_x_direction = InsightDirection.Up
                  #Else we do nothing
                else:
                    continue
                
                
            #If we have liqudiated or done nothing, set ifinvested and state to 0   
            if stock_x_direction and stock_y_direction == 0:
                symbolData.IfInvested = 0
                symbolData.State = 0
            
            #If we have gone short the spread, set the following parameteres    
            elif stock_x_direction == -1 and stock_y_direction == 1:
                symbolData.IfInvested = 1
                symbolData.State = -1
            
            #If we have gone long the spread, set the following parameteres    
            elif stock_x_direction == 1 and stock_y_direction == -1:
                symbolData.IfInvested = 1
                symbolData.State = 1
                
              
            #Set our insights to the right ticker       
            insight_y = Insight(stock_y, self.predictionInterval, InsightType.Price, stock_y_direction)
            insight_x = Insight(stock_x, self.predictionInterval, InsightType.Price, stock_x_direction)
            
            #this is not necessary
            updated_dict = (stock_x, stock_y)
            symbolData.pair_symbol = updated_dict
            
            #If we have changed state (bought, or liqudiated) we extend the insight list
            if symbolData.State != previous_state:
                insights.extend(Insight.Group(insight_y, insight_x))
                algorithm.Log(f"Pairs of traded stocks is {stock_y} and {stock_x}, and the direction is {symbolData.State}")
            
        return insights
    
                
    def OnSecuritiesChanged(self, algorithm, changes):
        #adding securities to self.securities
        for security in changes.AddedSecurities:
            self.Security.append(security)
            
        
        #logic for removing securities from self.securities
        for security in changes.RemovedSecurities:
            if security in self.Security:
                self.Security.remove(security)

        #Logic to remove securities from the self.pair
        for security in changes.RemovedSecurities:
            
            del_keys = []
            
            #For removing securities in the self.pairs
            for key, symbolData, in self.pairs.items():
                if security in symbolData.pair_symbol:
                    del_keys.append(key)
 
            for key in del_keys:
                self.pairs.pop(key)
                
        #update the pairs        
        self.UpdatePairs(algorithm)
        
        
    def UpdatePairs(self, algorithm):
        #use the list of the active tickers in our univers
        symbols = [x.Symbol for x in self.Security]
        
        #
        #
        #This is maybe wrong logic, have to double check!!!!!
        for i in range(0, len(symbols), 2):
            asset_i = symbols[i]
            
            asset_ii = symbols[i+1]
            pair_symbol = (asset_i, asset_ii)
                
            if len(pair_symbol) != 2:
                continue
                
                #hvis at vores pairs allerede er i eksisterende aktier, så går vi ud af funktionen
            if pair_symbol in self.pairs.values():
                continue
                
            self.pairs[i] = symbolData(pair_symbol)
        #
        #
        #
        
    def PairsToListAndHistory(self, algorithm, pair):
        #set the stocks in the list
        stocks = list(pair)
        stock1 = stocks[0]
        stock2 = stocks[1]
        #get the price data for the stocks
        df1 = algorithm.History(stock1, self.lookback, self.resolution)
        df2 = algorithm.History(stock2, self.lookback, self.resolution)
        #good solution the melt the dataframes together in a thight and fast way. Uses pandas
        history = pd.concat([df1, df2], axis=0)
        history = history['close'].unstack(level=0)
        history = history.dropna(axis=1)
        #Return the stock stocks, and the history of the 2 stocks
        return history, stock1, stock2


    
    def setKalman(self, df, stock1, stock2):
        #set the data for the stocks as y and x
        x = df[stock1]
        y = df[stock2]
    
        #Make a dataframe, that melt them together
        df1 = pd.DataFrame({'y':y, 'x':x})
        #Set index
        df1.index = pd.to_datetime(df1.index)
    
        #Get the kalman filter and calculate the spread
        state_means = self.regression(self.avg(x), self.avg(y))
        df1['hr'] = - state_means[:, 0]
        df1['spread'] =  df1.y + (df1.x * df1.hr)
    
        #Set theta and mean
        dt = 1
        mu = np.average(df1.spread)
        theta = 1
        
        #Set the standard deviation and variance
        sigma = np.std(df1['spread'])
        ts = np.arange(0, len(df1['spread'].values), dt)
        var = np.array([sigma**2 / (2 * theta) * (1-np.exp(-2 * theta * t)) for t in ts])
        std = 2 * np.sqrt(var)
        std = std[-1]
        
        #Calculate the upper and lower threshold
        upper = mu + std
        lower = mu - std
        
        #Return the last spread data, lower, mean and upper
        return df1.spread[-1], lower, mu, upper
        
    #calculate kalman avg
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
    
    #calculate kalman of the 2 stocks
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
    
    #Set the state, pairs and ifInvested
    def __init__(self, pair_symbol):
        self.pair_symbol = pair_symbol
        self.State = State.FlatRatio
        self.IfInvested = 0

#The state class
class State(Enum):
    ShortRatio = -1
    FlatRatio = 0
    LongRatio = 1
