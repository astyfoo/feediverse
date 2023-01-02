from setuptools import setup

with open("README.md") as f:
    long_description = f.read()

setup(
    name='feediverse',
    version='0.3.0',
    python_requires='>=3.3',
    url='https://github.com/ferdinandosimonetti/feediverse',
    author='Ed Summers',
    author_email='ehs@pobox.com',
    py_modules=['feediverse', ],
    description='Connect an RSS Feed to Mastodon or Misskey/Calckey',
    long_description=long_description,
    long_description_content_type="text/markdown",
    install_requires=['beautifulsoup4',
                      'feedparser',
                      'mastodon.py',
                      'Misskey.py',
                      'python-dateutil',
                      'pyyaml'],
    entry_points={'console_scripts': ['feediverse = feediverse:main']}
)
