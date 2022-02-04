from setuptools import find_packages, setup

from twcli.utils import VERSION


f = open('README.md', 'r')
LONG_DESCRIPTION = f.read()
f.close()

setup(
    name='tastyworks-cli',
    version=VERSION,
    description='An easy-to-use command line interface for Tastyworks!',
    long_description=LONG_DESCRIPTION,
    long_description_content_type='text/markdown',
    author='Graeme Holliday',
    author_email='graeme.holliday@pm.me',
    url='https://github.com/Graeme22/tastyworks-cli/',
    license='MIT',
    install_requires=[
        'asyncclick>=8.0.1.3',
        'anyio>=3.3.0',
        'matplotlib>=3.4.2',
        'QuantLib>=1.21',
        'pandas>=1.3.1',
        'petl>=1.7.4',
        'python-dateutil>=2.8.1',
        'rich>=11.0.0',
        'tastyworks-api>=4.2.2',
    ],
    packages=find_packages(exclude=['ez_setup', 'tests*']),
    include_package_data=True,
    entry_points="""
        [console_scripts]
        twcli = twcli.app:main
    """,
)
