"""Seed the tickers table with the 50 names we track in v1."""
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.db import session_scope
from app.models import Ticker

TICKERS = [
    ("NVDA", "NVIDIA Corp", "Technology", "Semiconductors", "NASDAQ"),
    ("AAPL", "Apple Inc", "Technology", "Consumer Electronics", "NASDAQ"),
    ("MSFT", "Microsoft Corp", "Technology", "Software", "NASDAQ"),
    ("GOOGL", "Alphabet Inc Class A", "Communication", "Internet", "NASDAQ"),
    ("META", "Meta Platforms", "Communication", "Social Media", "NASDAQ"),
    ("AMZN", "Amazon.com Inc", "Consumer Discretionary", "E-commerce", "NASDAQ"),
    ("TSLA", "Tesla Inc", "Consumer Discretionary", "Autos", "NASDAQ"),
    ("AMD", "Advanced Micro Devices", "Technology", "Semiconductors", "NASDAQ"),
    ("NFLX", "Netflix Inc", "Communication", "Streaming", "NASDAQ"),
    ("AVGO", "Broadcom Inc", "Technology", "Semiconductors", "NASDAQ"),

    ("JPM", "JPMorgan Chase", "Financials", "Banks", "NYSE"),
    ("BAC", "Bank of America", "Financials", "Banks", "NYSE"),
    ("GS", "Goldman Sachs", "Financials", "Investment Banks", "NYSE"),
    ("V", "Visa Inc", "Financials", "Payments", "NYSE"),
    ("MA", "Mastercard Inc", "Financials", "Payments", "NYSE"),

    ("XOM", "Exxon Mobil", "Energy", "Integrated Oil", "NYSE"),
    ("CVX", "Chevron Corp", "Energy", "Integrated Oil", "NYSE"),
    ("OXY", "Occidental Petroleum", "Energy", "Oil & Gas E&P", "NYSE"),

    ("UNH", "UnitedHealth Group", "Healthcare", "Managed Care", "NYSE"),
    ("LLY", "Eli Lilly & Co", "Healthcare", "Pharma", "NYSE"),
    ("JNJ", "Johnson & Johnson", "Healthcare", "Pharma", "NYSE"),
    ("PFE", "Pfizer Inc", "Healthcare", "Pharma", "NYSE"),

    ("DIS", "Walt Disney Co", "Communication", "Media", "NYSE"),
    ("UBER", "Uber Technologies", "Industrials", "Mobility", "NYSE"),
    ("SHOP", "Shopify Inc", "Technology", "E-commerce", "NYSE"),
    ("COIN", "Coinbase Global", "Financials", "Crypto", "NASDAQ"),
    ("PLTR", "Palantir Tech", "Technology", "Data & AI", "NYSE"),
    ("INTC", "Intel Corp", "Technology", "Semiconductors", "NASDAQ"),
    ("F", "Ford Motor", "Consumer Discretionary", "Autos", "NYSE"),
    ("GM", "General Motors", "Consumer Discretionary", "Autos", "NYSE"),
    ("BA", "Boeing Co", "Industrials", "Aerospace", "NYSE"),
    ("LMT", "Lockheed Martin", "Industrials", "Defense", "NYSE"),

    ("CRM", "Salesforce Inc", "Technology", "Software", "NYSE"),
    ("ORCL", "Oracle Corp", "Technology", "Software", "NYSE"),
    ("ADBE", "Adobe Inc", "Technology", "Software", "NASDAQ"),
    ("CRWD", "CrowdStrike Holdings", "Technology", "Cybersecurity", "NASDAQ"),
    ("SNOW", "Snowflake Inc", "Technology", "Data Cloud", "NYSE"),
    ("DDOG", "Datadog Inc", "Technology", "Observability", "NASDAQ"),

    ("SOFI", "SoFi Technologies", "Financials", "Fintech", "NASDAQ"),
    ("HOOD", "Robinhood Markets", "Financials", "Fintech", "NASDAQ"),
    ("PYPL", "PayPal Holdings", "Financials", "Payments", "NASDAQ"),
    ("ABNB", "Airbnb Inc", "Consumer Discretionary", "Travel", "NASDAQ"),
    ("BKNG", "Booking Holdings", "Consumer Discretionary", "Travel", "NASDAQ"),

    ("WMT", "Walmart Inc", "Consumer Staples", "Retail", "NYSE"),
    ("COST", "Costco Wholesale", "Consumer Staples", "Retail", "NASDAQ"),
    ("KO", "Coca-Cola Co", "Consumer Staples", "Beverages", "NYSE"),

    ("NEE", "NextEra Energy", "Utilities", "Renewables", "NYSE"),
    ("CAT", "Caterpillar Inc", "Industrials", "Machinery", "NYSE"),

    ("MSTR", "MicroStrategy", "Technology", "Software / BTC", "NASDAQ"),
    ("RIVN", "Rivian Automotive", "Consumer Discretionary", "EV", "NASDAQ"),
]


def seed() -> None:
    with session_scope() as db:
        for symbol, name, sector, industry, exchange in TICKERS:
            stmt = pg_insert(Ticker).values(
                symbol=symbol, name=name, sector=sector, industry=industry, exchange=exchange,
            ).on_conflict_do_update(
                index_elements=["symbol"],
                set_={"name": name, "sector": sector, "industry": industry, "exchange": exchange},
            )
            db.execute(stmt)
    print(f"Seeded {len(TICKERS)} tickers.")


if __name__ == "__main__":
    seed()
