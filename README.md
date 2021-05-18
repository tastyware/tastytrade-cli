# tastyworks-cli

An easy-to-use command line interface for Tastyworks!

## Installation

Currently unavailable pending the alpha release:
```
$ pip install tastyworks-cli
```

## Usage

Available commands:
```
tw plot                chart your portfolio's net liquidity or profit/loss over time
tw quant               mathematical and statistical analysis
tw order               view, replace, and cancel orders
tw watchlist           view current prices and other data for symbols in your watchlists
tw portfolio           view statistics and risk metrics for your portfolio
tw crypto              buy, sell, and analyze cryptocurrencies
tw future              buy, sell, and analyze futures
tw stock               buy, sell, and analyze stock
tw option              buy, sell, and analyze options
```
For more options, run `tw --help`.

## Development/Contributing

This project includes a number of helpers in the `Makefile` to streamline common development tasks.

Creating a virtualenv for development:
```
$ make venv
$ source env/bin/activate
```

It's usually a good idea to make sure you're passing tests locally before submitting a PR:
```
$ make test
```

If you have a feature suggestion, find a bug, or would like to contribute, feel free to open an issue or create a pull request.

## Disclaimer

tastyworks and tastytrade are not affiliated with the makers of this program and do not endorse this product. This program does not provide investment, tax, or legal advice. Stock trading involves risk and is not suitable for all investors. Options involve risk and are not suitable for all investors as the special risks inherent to options trading may expose investors to potentially significant losses. Futures and futures options trading is speculative and is not suitable for all investors. Cryptocurrency trading is speculative and is not suitable for all investors.
