# An easy-to-use command line interface for Tastyworks!

## Installation

```
$ pip install -r requirements.txt

$ pip install setup.py
```

## Development

This project includes a number of helpers in the `Makefile` to streamline common development tasks.

### Environment Setup

The following demonstrates setting up and working with a development environment:

```
### create a virtualenv for development

$ make virtualenv

$ source env/bin/activate


### run twcli cli application

$ twcli --help


### run pytest / coverage

$ make test
```


### Releasing to PyPi

Before releasing to PyPi, you must configure your login credentials:

**~/.pypirc**:

```
[pypi]
username = YOUR_USERNAME
password = YOUR_PASSWORD
```

Then use the included helper function via the `Makefile`:

```
$ make dist

$ make dist-upload
```

## Deployments

### Docker

Included is a basic `Dockerfile` for building and distributing `tastyworks-cli`,
and can be built with the included `make` helper:

```
$ make docker

$ docker run -it twcli --help
```

### Usage
Project is still in early development.
Conceptually the CLI should be split into the following subcomponents:

- watchlist           Display and sort information about symbols from one of your watchlists.
- portfolio           View data about your portfolio as a whole and assess portfolio risk.
- option              Lookup, buy, or sell options.
- stock               Lookup, buy, or sell stocks.
- future              Lookup, buy, or sell futures.
- order               View, replace, and cancel recent orders.

### Contributing
If you have a feature suggestion, find a bug, or would like to contribute, feel free to open an issue or create a pull request.
