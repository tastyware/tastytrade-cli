# tastyworks-cli

An easy-to-use command line interface for Tastyworks!

![Peek2024-07-0120-35-ezgif com-speed](https://github.com/tastyware/tastytrade-cli/assets/4185684/3d00731c-8f5e-40c5-973a-0f0357637083)

## Installation

```
$ pip install tastytrade-cli
```

> [!WARNING]  
> The CLI is still under active development. Please report any bugs, and contributions are always welcome!

## Usage

Available commands:
```
tt option              buy, sell, and analyze options
```
Unavailable commands pending development:
```
tt crypto              buy, sell, and analyze cryptocurrencies
tt future              buy, sell, and analyze futures
tt stock               buy, sell, and analyze stock
tt order               view, replace, and cancel orders
tt pf (portfolio)      view statistics and risk metrics for your portfolio
tt wl (watchlist)      view current prices and other data for symbols in your watchlists
```
For more options, run `tt --help` or `tt <subcommand> --help`.

## Development/Contributing

This project includes a number of helpers in the `Makefile` to streamline common development tasks.

Creating a virtualenv for development:
```
$ make venv
$ source .venv/bin/activate
```

It's usually a good idea to make sure you're passing tests locally before submitting a PR:
```
$ make lint
```

If you have a feature suggestion, find a bug, or would like to contribute, feel free to open an issue or create a pull request.

## Disclaimer

tastyworks and tastytrade are not affiliated with the makers of this program and do not endorse this product. This program does not provide investment, tax, or legal advice. Stock trading involves risk and is not suitable for all investors. Options involve risk and are not suitable for all investors as the special risks inherent to options trading may expose investors to potentially significant losses. Futures and futures options trading is speculative and is not suitable for all investors. Cryptocurrency trading is speculative and is not suitable for all investors.
