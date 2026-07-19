"""Fetch OHLCV data from Yahoo Finance."""
import yfinance as yf


def fetch(ticker: str, days: int = 30) -> "pd.DataFrame":
    df = yf.download(ticker, period=f"{days}d", interval="1d", progress=False, auto_adjust=True)
    if df.empty:
        raise ValueError(f"No data for {ticker}")
    return df["Close"].squeeze()  # Series of closing prices
