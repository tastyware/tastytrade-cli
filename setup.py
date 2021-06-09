from setuptools import find_packages, setup

from src.utils import VERSION


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
        'cement>=3.0.4',
        'tastyworks==4',
        'matplotlib>=3.4.2',
        'pandas>=1.2.4',
        'QuantLib>=1.21',
        'python-dateutil>=2.8.1'
    ],
    packages=find_packages(exclude=['ez_setup', 'tests*']),
    include_package_data=True,
    entry_points="""
        [console_scripts]
        tw = src.app:main
    """,
)
