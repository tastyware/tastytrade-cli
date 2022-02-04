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
        'asyncclick>=8.0.3.2',
        'matplotlib>=3.5.1',
        'pandas>=1.4.0',
        'petl>=1.7.7',
        'python-dateutil>=2.8.2',
        'rich>=11.1.0',
        'QuantLib>=1.25',
        'tastyworks-api>=4.2.2',
    ],
    packages=find_packages(exclude=['ez_setup', 'tests*']),
    include_package_data=True,
    entry_points="""
        [console_scripts]
        twcli = twcli.app:main
    """,
)
