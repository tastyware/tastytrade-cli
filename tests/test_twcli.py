from src.app import TastyworksCLITest


def test_twcli():
    # test twcli without any subcommands or arguments
    with TastyworksCLITest() as app:
        app.run()
        assert app.exit_code == 0


def test_twcli_debug():
    # test that debug mode is functional
    argv = ['--debug']
    with TastyworksCLITest(argv=argv) as app:
        app.run()
        assert app.debug is True
