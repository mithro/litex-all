import re
import os.path
import setuptools

SOURCE_URL_RE=re.compile(
    "(?P<first_quote>['\"])Source(?P=first_quote)\s*:(?P<url>[\s(]*((?P<second>['\"]).*?(?P=second)[\s\\\\)]*)+?)[,}]", re.DOTALL)


def get_setup_source_url(setup_py_data):
    """

    Basic example
    >>> get_setup_source_url('''
    ... <random stuff>,
    ... setup(
    ...   <more random stuff>
    ...   project_urls={  # Optional
    ...    'Bug Reports': 'https://github.com/pypa/sampleproject/issues',
    ...    'Funding': 'https://donate.pypi.org',
    ...    'Say Thanks!': 'http://saythanks.io/to/example',
    ...    'Source': 'https://github.com/pypa/sampleproject/',
    ...   },
    ...   <even more random stuff>
    ... )
    ... <final random stuff>
    ... ''')
    'https://github.com/pypa/sampleproject/'

    Support line continuations
    >>> get_setup_source_url('''
    ... <random stuff>,
    ... setup(
    ...   <more random stuff>
    ...   project_urls={  # Optional
    ...    'Bug Reports': 'https://github.com/pypa/sampleproject/issues',
    ...    'Funding': 'https://donate.pypi.org',
    ...    'Say Thanks!': 'http://saythanks.io/to/example',
    ...    'Source': ('https://github.com/pypa/'
    ...         'sampleproject/'),
    ...   },
    ...   <even more random stuff>
    ... )
    ... <final random stuff>
    ... ''')
    'https://github.com/pypa/sampleproject/'
    >>> get_setup_source_url('''
    ... <random stuff>,
    ... setup(
    ...   <more random stuff>
    ...   project_urls={  # Optional
    ...    'Bug Reports': 'https://github.com/pypa/sampleproject/issues',
    ...    'Funding': 'https://donate.pypi.org',
    ...    'Say Thanks!': 'http://saythanks.io/to/example',
    ...    'Source': ('https://github.com/pypa/\\\\
    ... sampleproject/'),
    ...   },
    ...   <even more random stuff>
    ... )
    ... <final random stuff>
    ... ''')
    'https://github.com/pypa/sampleproject/'

    Support triple quoted strings
    >>> get_setup_source_url('''
    ... <random stuff>,
    ... setup(
    ...   <more random stuff>
    ...   project_urls={  # Optional
    ...    'Bug Reports': 'https://github.com/pypa/sampleproject/issues',
    ...    'Funding': 'https://donate.pypi.org',
    ...    'Say Thanks!': 'http://saythanks.io/to/example',
    ...    'Source': \\'\\'\\'https://github.com/pypa/sampleproject/\\'\\'\\',
    ...   },
    ...   <even more random stuff>
    ... )
    ... <final random stuff>
    ... ''')
    'https://github.com/pypa/sampleproject/'
    >>> get_setup_source_url('''
    ... <random stuff>,
    ... setup(
    ...   <more random stuff>
    ...   project_urls={  # Optional
    ...    'Bug Reports': 'https://github.com/pypa/sampleproject/issues',
    ...    'Funding': 'https://donate.pypi.org',
    ...    'Say Thanks!': 'http://saythanks.io/to/example',
    ...    'Source': \\"\\"\\"\\
    ... https://github.com/pypa/sampleproject/\\"\\"\\",
    ...   },
    ...   <even more random stuff>
    ... )
    ... <final random stuff>
    ... ''')
    'https://github.com/pypa/sampleproject/'

    """
    braces = 0
    project_urls_data = []

    file_data = iter(setup_py_data.splitlines(keepends=True))
    while True:
        try:
            line = ""
            while not line.strip().startswith("project_urls"):
                line = next(file_data)

            braces = 0
            while braces > 0 or not project_urls_data:
                braces += line.count('{')
                braces -= line.count('}')
                project_urls_data.append(line)
                line = next(file_data)

        except StopIteration:
            break

    assert project_urls_data, setup_py_data

    m = SOURCE_URL_RE.search("".join(x.lstrip() for x in project_urls_data))
    assert m, project_urls_data
    assert m.group('url'), m

    url_str = m.group('url')
    try:
        url_value = eval(url_str)
    except SyntaxError as e:
        raise ValueError('Invalid source URL ' + repr(url_str) + ' ' + str(e))

    return url_value



MODULES_SETUP = {}


def import_setup_py(setup_py):
    setuptools._setup = setuptools.setup
    try:
        def fake_setup(name, **kw):
            MODULES_SETUP[name] = kw
        setuptools.setup = fake_setup

        MODULES_SETUP.clear()
        setup_dir = os.path.dirname(setup_py)
        try:
            sys.path.insert(setup_dir)
            exec("import setup")
            print(MODULES_SETUP)
            for m in MODULES_SETUP:
                return m, MODULES_SETUP
        finally:
            sys.path.pop(0)
    finally:
        setuptools.setup = setuptools._setup



def trees():
    for d in sorted(os.listdir()):
        if not os.path.isdir(d):
            continue
        setup_py = os.path.join(d, 'setup.py')
        if not os.path.exists(setup_py):
            continue
        import_setup_py(setup_py)
        yield d, get_setup_source_url(open(setup_py).read())


if __name__ == "__main__":
    import doctest
    doctest.testmod()
    for d, src in trees():
        print(d, "is from", src)
