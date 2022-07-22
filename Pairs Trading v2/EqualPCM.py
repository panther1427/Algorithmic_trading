#region imports
from AlgorithmImports import *
#endregion
from QuantConnect import Resolution, Extensions
from QuantConnect.Algorithm.Framework.Alphas import *
from QuantConnect.Algorithm.Framework.Portfolio import *
from itertools import groupby
from datetime import datetime, timedelta
from pytz import utc
UTCMIN = datetime.min.replace(tzinfo=utc)
#endregion
class EqualWeightedPairsTradingPortfolio(PortfolioConstructionModel):
    def __init__(self):
        
        self.insightCollection = InsightCollection()
        self.removedSymbols = []
        

    def CreateTargets(self, algorithm, insights):

        targets = []

        if len(insights) == 0:
            return targets
        
        # here we get the new insights and add them to our insight collection
        for insight in insights:
            self.insightCollection.Add(insight)
            
        # create flatten target for each security that was removed from the universe
        if len(self.removedSymbols) > 0:
            #check if the tickers is in invested, otherwise, do nothing
            universeDeselectionTargets = [PortfolioTarget(symbol, 0) for symbol in self.removedSymbols if algorithm.Portfolio[symbol].Invested]

            self.removedSymbols = []

            pop_insights = []
            #If we have something in the universeDeselectionTargets
            if universeDeselectionTargets:
                #loop over the targets
                for target in universeDeselectionTargets:
                    #If the symbol is in our insightCollection then we have to remove that insight
                    if self.insightCollection.ContainsKey(target.Symbol):
                        #Get a list of the insights (there maybe more than 1)
                        insights_list = self.insightCollection[target.Symbol]
                        #loop over the insights
                        for insight in insights_list:
                            #loop over the insights in insightcollection
                            for insightCollection in self.insightCollection:
                                #if the insights have been send together (.GroupId), we liquidate both stocks and send the insights to a list, to remove those insights from the collection
                                if insight.GroupId == insightCollection.GroupId:
                                    targets.extend([PortfolioTarget(insight.Symbol, 0)] + [PortfolioTarget(insightCollection.Symbol, 0)])
                                    pop_insights.extend([insight] + [insightCollection])

            for insight in pop_insights:
                self.insightCollection.Remove(insight)
        
        #Get the expired insights
        expiredInsights = self.insightCollection.RemoveExpiredInsights(algorithm.UtcTime)

        #loop over the insights. If the symbol does NOT have an active insight, we can liquidate this stock
        for symbol, f in groupby(expiredInsights, lambda x: x.Symbol):
            if not self.insightCollection.HasActiveInsights(symbol, algorithm.UtcTime):
                targets.append(PortfolioTarget(symbol, 0))
        
        # get insight that have not expired of each symbol that is still in the universe
        activeInsights = self.insightCollection.GetActiveInsights(algorithm.UtcTime)

        #sort by the most recent insight generated, so it is only the first insights being generated that is being used
        lastActiveInsights = sorted(activeInsights, key= lambda x: x.GeneratedTimeUtc, reverse=True)

        #get the len of the active insights, and loop over the insights 
        pairs = {}
        for i in range(len(lastActiveInsights)):
            for ii in range(i+1, len(lastActiveInsights)):
                #get the insights
                insight_i = lastActiveInsights[i]
                insight_ii = lastActiveInsights[ii]
                
                #get the pairs
                pairs_symbol = (insight_i.Symbol, insight_ii.Symbol)
                invert = (insight_ii.Symbol, insight_i.Symbol)

                #if the stocks is already in the pairs, continue
                if pairs_symbol in pairs or invert in pairs:
                    continue
                
                #If the insights is of the same groupId, we know that these belong together, so we append to the pairs
                if insight_i.GroupId == insight_ii.GroupId:
                    pairs[(pairs_symbol)] = [insight_i.Direction, insight_ii.Direction]                

        #Here, we calculated the score of the insights
        calculatedTargets = {}
        for key, value in pairs.items():
            for insight, direction in zip(key, value):
                if insight not in calculatedTargets:
                    calculatedTargets[insight] = direction
                else:
                    calculatedTargets[insight] += direction
            

        # determine target percent for the given insights
        weightFactor = 1.0
        weightSums = sum(abs(direction) for symbol, direction in calculatedTargets.items())


        if weightSums > 1:
            weightFactor = 1 / weightSums

        #Send the portfolio targets out, with the correct allocation percent, and append to the targets
        for symbol, weight in calculatedTargets.items():
            allocationPercent = weight * weightFactor
            target = PortfolioTarget.Percent(algorithm, symbol, allocationPercent)
            targets.append(target)

        return targets
        
    def OnSecuritiesChanged(self, algorithm, changes):
        
        #Get the removed symbols
        newRemovedSymbols = [x.Symbol for x in changes.RemovedSecurities if x.Symbol not in self.removedSymbols]
        
        # get removed symbol and invalidate them in the insight collection
        self.removedSymbols.extend(newRemovedSymbols)

        #remove insights that have not been invested in anymore
        not_invested_symbols = [symbol for symbol in self.removedSymbols if not algorithm.Portfolio[symbol].Invested]
        self.insightCollection.Clear(not_invested_symbols)
            
