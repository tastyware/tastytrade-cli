# tastyworks-cli

An easy-to-use command line interface for Tastyworks!

## Installation

```
$ pip install tastyworks-cli
```

## Usage

Available commands:
```
twcli option              buy, sell, and analyze options
twcli plot                chart your portfolio's net liquidity or profit/loss over time
```
Unavailable commands pending development:
```
twcli crypto              buy, sell, and analyze cryptocurrencies
twcli future              buy, sell, and analyze futures
twcli order               view, replace, and cancel orders
twcli pairs               analyze and size pairs trades
twcli portfolio           view statistics and risk metrics for your portfolio
twcli quant               mathematical and statistical analysis
twcli stock               buy, sell, and analyze stock
twcli watchlist           view current prices and other data for symbols in your watchlists
```
For more options, run `twcli --help` or `twcli <subcommand> --help`.

## Development/Contributing

This project includes a number of helpers in the `Makefile` to streamline common development tasks.

Creating a virtualenv for development:
```
$ make venv
$ source env/bin/activate
```

Install the package: 

```
$ pip install -e . 
```

It's usually a good idea to make sure you're passing tests locally before submitting a PR:
```
$ make test
```

If you have a feature suggestion, find a bug, or would like to contribute, feel free to open an issue or create a pull request.

## Disclaimer

tastyworks and tastytrade are not affiliated with the makers of this program and do not endorse this product. This program does not provide investment, tax, or legal advice. Stock trading involves risk and is not suitable for all investors. Options involve risk and are not suitable for all investors as the special risks inherent to options trading may expose investors to potentially significant losses. Futures and futures options trading is speculative and is not suitable for all investors. Cryptocurrency trading is speculative and is not suitable for all investors.
