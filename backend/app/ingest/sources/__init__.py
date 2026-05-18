"""Source registry. Workers iterate the lists below — add a new source by
appending it to either tuple.

Per-ticker sources hit one URL per tracked symbol (rate-limited inside the
worker). Global sources fetch once per cycle and rely on the regex tagger."""
from .base import RawArticle, Source  # noqa: F401
from .finnhub_source import FinnhubCompanyNews, FinnhubGeneralNews
from .yahoo import YahooFinanceRSS
from .sec_edgar import SecEdgarFilings
from .google_news import GoogleNewsRSS
from .reddit import RedditDiscussions
from .hackernews import HackerNewsSearch

PER_TICKER_SOURCES = [
    FinnhubCompanyNews(),
    YahooFinanceRSS(),
    SecEdgarFilings(),
    GoogleNewsRSS(),
]

GLOBAL_SOURCES = [
    FinnhubGeneralNews(),
    RedditDiscussions(),
    HackerNewsSearch(),
]
