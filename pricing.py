import math

STRIKE_INCREMENT = 5

# ============================================================================
# BLACK-SCHOLES
# ============================================================================

def norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def black_scholes_price(S, K, T, r, sigma, option_type='call'):
    if T <= 0:
        return max(0, S - K) if option_type == 'call' else max(0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option_type == 'call':
        return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    else:
        return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)


def black_scholes_delta(S, K, T, r, sigma, option_type='call'):
    if T <= 0:
        if option_type == 'call':
            return 1.0 if S > K else 0.0
        return -1.0 if S < K else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return norm_cdf(d1) if option_type == 'call' else norm_cdf(d1) - 1


def find_strike_for_delta(S, target_delta, T, r, sigma, option_type='put'):
    target = abs(target_delta) / 100.0
    if option_type == 'put':
        low_k, high_k = S * 0.6, S * 1.0
        mid_k = (low_k + high_k) / 2
        for _ in range(60):
            mid_k = (low_k + high_k) / 2
            d = abs(black_scholes_delta(S, mid_k, T, r, sigma, 'put'))
            if abs(d - target) < 0.001:
                break
            if d > target: high_k = mid_k
            else:          low_k  = mid_k
        return round(mid_k / STRIKE_INCREMENT) * STRIKE_INCREMENT
    else:
        low_k, high_k = S * 1.0, S * 1.4
        mid_k = (low_k + high_k) / 2
        for _ in range(60):
            mid_k = (low_k + high_k) / 2
            d = black_scholes_delta(S, mid_k, T, r, sigma, 'call')
            if abs(d - target) < 0.001:
                break
            if d > target: low_k  = mid_k
            else:          high_k = mid_k
        return round(mid_k / STRIKE_INCREMENT) * STRIKE_INCREMENT
