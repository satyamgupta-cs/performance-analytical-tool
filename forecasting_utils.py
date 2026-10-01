import numpy as np
import pandas as pd
from scipy.stats import linregress


def analyze_trend_and_forecast(monthly_df, score_col="Overall_Score"):
    """Calculates trend trajectory, 3-month growth, and predicts the next

    month's score using Ordinary Least Squares (OLS) Linear Regression.
    """
    if monthly_df is None or len(monthly_df) < 2:
        current = (
            monthly_df[score_col].iloc[-1]
            if monthly_df is not None and not monthly_df.empty
            else 0.0
        )
        return {
            "trend": "Insufficient Data",
            "current_score": current,
            "growth_3m": 0.0,
            "predicted_next": current,
            "slope": 0.0,
            "r_squared": 0.0,
        }

    df = monthly_df.copy()
    scores = df[score_col].values
    n = len(scores)

    # Convert time sequence to sequential integer indices [1, 2, ..., n]
    x = np.arange(1, n + 1)
    y = scores

    # Compute Ordinary Least Squares Linear Regression
    slope, intercept, r_value, p_value, std_err = linregress(x, y)

    # Predict Next Month (index = n + 1)
    next_month_idx = n + 1
    raw_pred = slope * next_month_idx + intercept

    # Clamp predicted score within logical limits [0, 100]
    pred_score = max(0.0, min(100.0, raw_pred))

    # Determine Trend Direction based on slope threshold
    if slope > 0.5:
        trend = "Improving"
    elif slope < -0.5:
        trend = "Declining"
    else:
        trend = "Stable"

    # Current Score
    current_score = scores[-1]

    # Calculate 3-Month Growth (or total growth if less than 4 months of records)
    if n >= 4:
        growth_3m = scores[-1] - scores[-4]
    else:
        growth_3m = scores[-1] - scores[0]

    return {
        "trend": trend,
        "current_score": round(current_score, 1),
        "growth_3m": round(growth_3m, 1),
        "predicted_next": round(pred_score, 1),
        "slope": round(slope, 2),
        "r_squared": round(r_value**2, 2),
    }