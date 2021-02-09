
from setuptools import setup, find_packages
from twcli.core.version import get_version

VERSION = get_version()

f = open('README.md', 'r')
LONG_DESCRIPTION = f.read()
f.close()

setup(
    name='twcli',
    version=VERSION,
    description='An easy-to-use command line interface for Tastyworks!',
    long_description=LONG_DESCRIPTION,
    long_description_content_type='text/markdown',
    author='Graeme Holliday',
    author_email='gholliday2@hotmail.com',
    url='https://github.com/Graeme22/tastyworks-cli/',
    license='MIT',
    packages=find_packages(exclude=['ez_setup', 'tests*']),
    package_data={'twcli': ['templates/*']},
    include_package_data=True,
    entry_points="""
        [console_scripts]
        twcli = twcli.main:main
    """,
)
