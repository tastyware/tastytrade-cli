from setuptools import find_packages, setup

f = open('README.md', 'r')
LONG_DESCRIPTION = f.read()
f.close()

setup(
    name='tastytrade-cli',
    version='0.1',
    description='An easy-to-use command line interface for Tastytrade!',
    long_description=LONG_DESCRIPTION,
    long_description_content_type='text/markdown',
    author='Graeme Holliday',
    author_email='graeme.holliday@pm.me',
    url='https://github.com/tastyware/tastytrade-cli',
    license='MIT',
    install_requires=[
        'asyncclick>=8.1.7.2',
        'rich>=13.7.1',
        'tastytrade>=7.7',
    ],
    data_files = [('etc', ['etc/ttcli.cfg'])],
    packages=find_packages(exclude=['ez_setup']),
    include_package_data=True,
    entry_points="""
        [console_scripts]
        tt = ttcli.app:main
    """
)
