from twcli.main import TastyworksCLITest


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


def test_command1():
    # test command1 without arguments
    argv = ['command1']
    with TastyworksCLITest(argv=argv) as app:
        app.run()
        data, output = app.last_rendered
        assert data['foo'] == 'bar'
        assert output.find('Foo => bar')

    # test command1 with arguments
    argv = ['command1', '--foo', 'not-bar']
    with TastyworksCLITest(argv=argv) as app:
        app.run()
        data, output = app.last_rendered
        assert data['foo'] == 'not-bar'
        assert output.find('Foo => not-bar')
