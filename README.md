# An easy-to-use command line interface for Tastyworks!

## Installation

Currently unavailable pending release:

```
$ pip install tastyworks-cli
```

## Development

This project includes a number of helpers in the `Makefile` to streamline common development tasks.
The following demonstrates setting up and working with a development environment:

```
### create a virtualenv for development
$ make venv
$ source env/bin/activate

### run twcli application
$ twcli --help

### run pytest / coverage
$ make test
```

### Usage
Project is still in early development.
Conceptually the CLI should be split into the following subcomponents:

- watchlist:           Display and sort information about symbols from one of your watchlists.
- portfolio:           View data about your portfolio as a whole and assess portfolio risk.
- option:              Lookup, buy, or sell options.
- stock:               Lookup, buy, or sell stocks.
- future:              Lookup, buy, or sell futures.
- order:               View, replace, and cancel recent orders.
- quant:               Quantitative analysis using `quantlib`
- plot:                Simple portfolio charting tools

### Contributing
If you have a feature suggestion, find a bug, or would like to contribute, feel free to open an issue or create a pull request.
