## ALL ALGORITHMS IS WRITTEN IN QUANTCONNECT ENGINE

Bollinger bands:

The bollinger bands algorithm mainly uses the bollinger bands indicator to buy or short different securities. It starts with picking the most volatile securities
that also has good liquidity, and then it scans the 10 securities for a chance to buy or short the securites, based on the bollinger bands. It liquides accordingly. 
The algo has NO riskmodel


Momentum framework, with risk model

The momentum framework buys securities that has done good over a long period of time. The model selects the 100 most liquid stocks, and selects the 10 stocks that have 
done the best. It is long only. The risk model is based on SPY, and an EMA. The logic is that all stocks have a high beta in bear markets. If the value of SPY falls below 
the EMA, we liquidate everything, and only holds cash
