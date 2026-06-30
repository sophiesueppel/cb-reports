"""
Shared watchlist topic definitions for the central bank speech tracker.

These 15 topics are scored by the LLM at rating time and stored in the
`topic_scores` DB column as a JSON dict {topic_name: 0 or 1}.
"""

WATCHLIST_TOPICS = [
    ("Middle East",        "Conflicts, instability, and oil supply risks centred on the Middle East including Iran, Israel, Gaza and the Gulf states"),
    ("Russia / Ukraine",   "The Russia-Ukraine war, Western sanctions on Russia, energy disruption in Europe, and reconstruction financing"),
    ("China",              "China's economic slowdown, property crisis, trade tensions with the West, capital controls, and RMB dynamics"),
    ("Taiwan",             "Taiwan Strait tensions, semiconductor supply risk, and geopolitical flashpoint scenarios"),
    ("Oil & Gas",          "Crude oil prices, natural gas markets, OPEC production decisions, and energy supply shocks"),
    ("Food & Agriculture", "Global food prices, grain supply disruptions, agricultural commodity markets, and food inflation"),
    ("Energy Transition",  "The shift to renewables, green energy investment, net zero commitments, and carbon pricing"),
    ("Tariffs",            "Import tariffs, trade wars, protectionism, and the economic impact of trade barriers"),
    ("Fiscal Policy",      "Government spending, budget deficits, fiscal stimulus, public debt sustainability, and sovereign risk"),
    ("Neutral Rate",       "The neutral or natural rate of interest, r-star estimates, and their implications for the rate path"),
    ("QT / Balance Sheet", "Quantitative tightening, balance sheet runoff, quantitative easing, and central bank asset purchases"),
    ("Yield Curve",        "The yield curve shape, term premium, curve inversion, and long-end rate dynamics"),
    ("AI & Productivity",  "Artificial intelligence, machine learning, automation, and their impact on productivity and the labour market"),
    ("Housing",            "Housing markets, mortgage rates, house prices, residential construction, and housing affordability"),
    ("Dollar / FX",        "The US dollar, exchange rates, reserve currency status, and currency depreciation or appreciation"),
]

WATCHLIST_NAMES = [name for name, _ in WATCHLIST_TOPICS]
