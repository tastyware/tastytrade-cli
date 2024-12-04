[![PyPI](https://img.shields.io/pypi/v/tastytrade-cli)](https://pypi.org/project/tastytrade-cli)
[![Downloads](https://static.pepy.tech/badge/tastytrade-cli)](https://pepy.tech/project/tastytrade-cli)
[![Release)](https://img.shields.io/github/v/release/tastyware/tastytrade-cli?label=release%20notes)](https://github.com/tastyware/tastytrade-cli/releases)

# tastytrade-cli

An easy-to-use command line interface for Tastytrade!

![Peek2024-12-0322-18-ezgif com-speed](https://github.com/user-attachments/assets/0ca9d3a0-19d4-4eac-bd4a-db78d62a991f)

## Installation

```
$ pip install tastytrade-cli
```

> [!WARNING]  
> The CLI is still under active development. Please report any bugs, and contributions are always welcome!

## Usage

Available commands:
```
tt option              view chains, buy or sell equities and futures options
tt pf (portfolio)      view and close positions, check margin and analyze BP usage
tt trade               buy or sell stocks/ETFs, crypto, and futures
```
Unavailable commands pending development:
```
tt order               view, replace, and cancel orders
tt wl (watchlist)      view current prices and other data for symbols in your watchlists
```
For more options, run `tt --help` or `tt <subcommand> --help`.

## Configuration

Many aspects of the CLI's behavior can be customized using the `ttcli.cfg` file generated upon the first usage of the CLI. The file is located in your OS's home directory followed by the path `.config/ttcli/ttcli.cfg`. If you don't know where that is, you can just run `python -c "from ttcli.utils import config_path; print(config_path)"`.

The default configuration file contains lots of options along with explanations of what they do.

## Shell completion
<details>
  <summary>Bash</summary>

Add this line to your `.bashrc`:
```bash
eval "$(_TT_COMPLETE=bash_source tt)"
```
</details>

<details>
  <summary>Zsh</summary>
  
Add this line to your `.zshrc`:
```zsh
eval "$(_TT_COMPLETE=zsh_source tt)"
```
</details>

<details>
  <summary>Fish</summary>
  
Add this to `~/.config/fish/completions/tt.fish`
```fish
_TT_COMPLETE=fish_source tt | source
```
</details>

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
