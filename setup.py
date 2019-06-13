from setuptools import setup, find_packages


setup(
    name='gatenlp',
    version='3.2.3',
    description='Interface for parsing and manipulating GATE annotation documents',
    url='http://github.com/nickwbarber/gatenlp',
    author='Nick Barber',
    author_email='nickwbarber@gmail.com',
    license='MIT',
    packages=find_packages(),
    install_requires=[
        'lxml==4.1.1',
        'intervaltree==2.1.0',
        'python-Levenshtein==0.12.0'
    ],
    python_requires='>=3',
    zip_safe=False,
)
