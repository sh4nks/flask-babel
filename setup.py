"""
Flask-Babel
-----------

Adds i18n/l10n support to Flask applications with the help of the
`Babel`_ library.

Links
`````

* `documentation <https://pythonhosted.org/Flask-Babel/>`_
* `development version
  <https://github.com/python-babel/flask-babel/archive/master.zip#egg=Flask-Babel-dev>`_

.. _Babel: http://babel.pocoo.org/

"""
from setuptools import setup


setup(
    name='Flask-Babel',
    version='0.11.2',
    url='https://github.com/python-babel/flask-babel',
    license='BSD',
    author='Armin Ronacher',
    author_email='armin.ronacher@active-4.com',
    description='Adds i18n/l10n support to Flask applications',
    long_description=__doc__,
    packages=['flask_babel'],
    zip_safe=False,
    platforms='any',
    install_requires=[
        'Flask',
        'Babel>=2.3',
        'Jinja2>=2.5'
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ]
)
