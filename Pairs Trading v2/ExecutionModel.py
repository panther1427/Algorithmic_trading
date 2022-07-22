from AlgorithmImports import *

class MarketOrderModel(ExecutionModel):

    def __init__(self):
        self.targetsCollection = PortfolioTargetCollection()

    def Execute(self, algorithm, targets):

        # for performance we check count value, OrderByMarginImpact and ClearFulfilled are expensive to call
        self.targetsCollection.AddRange(targets)
        if self.targetsCollection.Count > 0:
            for target in self.targetsCollection.OrderByMarginImpact(algorithm):
                security = algorithm.Securities[target.Symbol]
                # calculate remaining quantity to be ordered
                quantity = OrderSizing.GetUnorderedQuantity(algorithm, target, security)
                if quantity != 0:
                    aboveMinimumPortfolio = BuyingPowerModelExtensions.AboveMinimumOrderMarginPortfolioPercentage(security.BuyingPowerModel, security, quantity, algorithm.Portfolio, algorithm.Settings.MinimumOrderMarginPortfolioPercentage)
                    if aboveMinimumPortfolio:
                        algorithm.MarketOrder(security, quantity)

            self.targetsCollection.ClearFulfilled(algorithm)
