# tastytrade-cli

An easy-to-use command line interface for Tastytrade!

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
tt option              view chains, buy/sell equities and futures options
tt pf (portfolio)      view & close positions, check margin and analyze BP usage
```
Unavailable commands pending development:
```
tt crypto              buy, sell, and analyze cryptocurrencies
tt future              buy, sell, and analyze futures
tt stock               buy, sell, and analyze stock
tt order               view, replace, and cancel orders
tt wl (watchlist)      view current prices and other data for symbols in your watchlists
```
For more options, run `tt --help` or `tt <subcommand> --help`.

## Configuration

TODO

## Shell completion

* Bash: Add this line to your `.bashrc`:
```bash
eval "$(_TT_COMPLETE=bash_source tt)"
```
* Zsh: Add this line to your `.zshrc`:
```zsh
eval "$(_TT_COMPLETE=zsh_source tt)"
```
* Fish: Add this to `~/.config/fish/completions/tt.fish`
```fish
_TT_COMPLETE=fish_source tt | source
```

## Development/Contributing

This project includes a number of helpers in the `Makefile` to streamline common development tasks.
Make sure you already have [uv](https://docs.astral.sh/uv/getting-started/installation/) installed!

Creating a virtualenv for development:
```
$ make install
```

It's usually a good idea to make sure you're passing tests locally before submitting a PR:
```
$ make lint
```

If you have a feature suggestion, find a bug, or would like to contribute, feel free to open an issue or create a pull request.

## Disclaimer

tastyworks and tastytrade are not affiliated with the makers of this program and do not endorse this product. This program does not provide investment, tax, or legal advice. Stock trading involves risk and is not suitable for all investors. Options involve risk and are not suitable for all investors as the special risks inherent to options trading may expose investors to potentially significant losses. Futures and futures options trading is speculative and is not suitable for all investors. Cryptocurrency trading is speculative and is not suitable for all investors.
