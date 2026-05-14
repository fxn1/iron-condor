import math


def calculate_historical_volatility(prices, window=20):
    if len(prices) < window + 1:
        return 0.18
    returns = [math.log(prices[i] / prices[i - 1])
               for i in range(1, len(prices)) if prices[i - 1] > 0]
    if len(returns) < window:
        return 0.18
    recent = returns[-window:]
    mean = sum(recent) / len(recent)
    var  = sum((r - mean) ** 2 for r in recent) / (len(recent) - 1)
    return math.sqrt(var) * math.sqrt(252)
