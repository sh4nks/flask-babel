# -*- coding: utf-8 -*-
"""
    flaskext.babel
    ~~~~~~~~~~~~~~

    Implements i18n/l10n support for Flask applications based on Babel.

    :copyright: (c) 2013 by Armin Ronacher, Daniel Neuhäuser.
    :license: BSD, see LICENSE for more details.
"""
from __future__ import absolute_import
import os

from datetime import datetime
from contextlib import contextmanager
from flask import current_app, request
from flask.ctx import has_request_context
from babel import dates, numbers, support, Locale
from werkzeug import ImmutableDict
try:
    from pytz.gae import pytz
except ImportError:
    from pytz import timezone, UTC
else:
    timezone = pytz.timezone
    UTC = pytz.UTC

from flask_babel._compat import string_types
from flask_babel.speaklater import LazyString


class Babel(object):
    """Central controller class that can be used to configure how
    Flask-Babel behaves.  Each application that wants to use Flask-Babel
    has to create, or run :meth:`init_app` on, an instance of this class
    after the configuration was initialized.
    """

    default_date_formats = ImmutableDict({
        'time':             'medium',
        'date':             'medium',
        'datetime':         'medium',
        'time.short':       None,
        'time.medium':      None,
        'time.full':        None,
        'time.long':        None,
        'date.short':       None,
        'date.medium':      None,
        'date.full':        None,
        'date.long':        None,
        'datetime.short':   None,
        'datetime.medium':  None,
        'datetime.full':    None,
        'datetime.long':    None,
    })

    def __init__(self, app=None, **kwargs):
        self.locale_selector_func = None
        self.timezone_selector_func = None
        self.app = app
        if app is not None:
            self.init_app(app, **kwargs)

    def init_app(self, app, default_locale='en', default_timezone='UTC',
                 default_domain='messages', date_formats=None,
                 configure_jinja=True):
        """Sets up the Flask-BabelEx extension.
        :param app: The Flask application.
        :param default_locale: The default locale which should be used.
        :param default_timezone: The default timezone.
        :param date_formats: A mapping of Babel datetime format strings
        :param configure_jinja: If set to ``True`` some convenient jinja2
                                filters are being added.
        :param default_domain: The default translation domain.
        """
        app.config.setdefault('BABEL_DEFAULT_LOCALE', default_locale)
        app.config.setdefault('BABEL_DEFAULT_TIMEZONE', default_timezone)
        app.config.setdefault('BABEL_DOMAIN', default_domain)
        app.config.setdefault('BABEL_TRANSLATION_DIRECTORIES', "translations")

        if date_formats is None:
            self.date_formats = self.default_date_formats.copy()
        else:
            #: a mapping of Babel datetime format strings that can be modified
            #: to change the defaults.  If you invoke :func:`format_datetime`
            #: and do not provide any format string Flask-Babel will do the
            #: following things:
            #:
            #: 1.   look up ``date_formats['datetime']``.
            #:      By default ``'medium'`` is returned to enforce medium
            #:      length datetime formats.
            #: 2.   ``date_formats['datetime.medium'] (if ``'medium'`` was
            #:      returned in step one) is looked up.  If the return value
            #:      is anything but `None` this is used as new format string.
            #:      otherwise the default for that language is used.
            self.date_formats = date_formats

        app.extensions = getattr(app, 'extensions', {})
        app.extensions['babel'] = self

        if configure_jinja:
            app.jinja_env.filters.update(
                datetimeformat=format_datetime,
                dateformat=format_date,
                timeformat=format_time,
                timedeltaformat=format_timedelta,

                numberformat=format_number,
                decimalformat=format_decimal,
                currencyformat=format_currency,
                percentformat=format_percent,
                scientificformat=format_scientific,
            )
            app.jinja_env.add_extension('jinja2.ext.i18n')
            app.jinja_env.install_gettext_callables(
                lambda x: get_translations().ugettext(x),
                lambda s, p, n: get_translations().ungettext(s, p, n),
                newstyle=True
            )

    def get_app(self, reference_app=None):
        """Helper method that implements the logic to look up an a
        pplication.
        """
        if reference_app is not None:
            return reference_app

        if self.app is not None:
            return self.app

        if current_app is not None:
            return current_app

        raise RuntimeError('application not registered on babel '
                           'instance and no application bound '
                           'to current context')

    def localeselector(self, f):
        """Registers a callback function for locale selection.  The default
        behaves as if a function was registered that returns `None` all the
        time.  If `None` is returned, the locale falls back to the one from
        the configuration.

        This has to return the locale as string (eg: ``'de_AT'``, ``'en_US'``)
        """
        assert self.locale_selector_func is None, \
            'a localeselector function is already registered'
        self.locale_selector_func = f
        return f

    def timezoneselector(self, f):
        """Registers a callback function for timezone selection.  The default
        behaves as if a function was registered that returns `None` all the
        time.  If `None` is returned, the timezone falls back to the one from
        the configuration.

        This has to return the timezone as string (eg: ``'Europe/Vienna'``)
        """
        assert self.timezone_selector_func is None, \
            'a timezoneselector function is already registered'
        self.timezone_selector_func = f
        return f

    def list_translations(self):
        """Returns a list of all the locales translations exist for.  The
        list returned will be filled with actual locale objects and not just
        strings.

        .. versionadded:: 0.6
        """
        result = []

        for dirname in self.translation_directories:
            if not os.path.isdir(dirname):
                continue

            for folder in os.listdir(dirname):
                locale_dir = os.path.join(dirname, folder, 'LC_MESSAGES')
                if not os.path.isdir(locale_dir):
                    continue

                if filter(lambda x: x.endswith('.mo'), os.listdir(locale_dir)):
                    result.append(Locale.parse(folder))

        # If not other translations are found, add the default locale.
        if not result:
            result.append(Locale.parse(self._default_locale))

        return result

    @property
    def default_locale(self):
        """The default locale from the configuration as instance of a
        `babel.Locale` object.
        """
        return Locale.parse(self.get_app().config['BABEL_DEFAULT_LOCALE'])

    @property
    def default_timezone(self):
        """The default timezone from the configuration as instance of a
        `pytz.timezone` object.
        """
        return timezone(self.get_app().config['BABEL_DEFAULT_TIMEZONE'])

    @property
    def domain(self):
        """The message domain for the translations as a string.
        """
        return self.get_app().config['BABEL_DOMAIN']

    @property
    def translation_directories(self):
        directories = self.get_app().config[
            'BABEL_TRANSLATION_DIRECTORIES'
        ].split(';')

        for path in directories:
            if os.path.isabs(path):
                yield path
            else:
                yield os.path.join(self.get_app().root_path, path)


def get_translations():
    """Returns the correct gettext translations that should be used for
    this request.  This will never fail and return a dummy translation
    object if used outside of the request or if a translation cannot be
    found.
    """
    ctx = _get_current_context()

    if ctx is None:
        return support.NullTranslations()

    translations = getattr(ctx, 'babel_translations', None)
    if translations is None:
        translations = support.Translations()

        babel = current_app.extensions['babel']
        for dirname in babel.translation_directories:
            catalog = support.Translations.load(
                    dirname,
                    [get_locale()],
                    babel.domain
                )
            translations.merge(catalog)
            # FIXME: Workaround for merge() being really, really stupid. It
            # does not copy _info, plural(), or any other instance variables
            # populated by GNUTranslations. We probably want to stop using
            # `support.Translations.merge` entirely.
            if hasattr(catalog, 'plural'):
                translations.plural = catalog.plural

        ctx.babel_translations = translations

    return translations


def get_locale():
    """Returns the locale that should be used for this request as
    `babel.Locale` object.  This returns `None` if used outside of
    a request.
    """
    ctx = _get_current_context()
    if ctx is None:
        return None
    locale = getattr(ctx, 'babel_locale', None)
    if locale is None:
        babel = current_app.extensions['babel']
        if babel.locale_selector_func is None:
            locale = babel.default_locale
        else:
            rv = babel.locale_selector_func()
            if rv is None:
                locale = babel.default_locale
            else:
                locale = Locale.parse(rv)
        ctx.babel_locale = locale
    return locale


def get_timezone():
    """Returns the timezone that should be used for this request as
    `pytz.timezone` object.  This returns `None` if used outside of
    a request.
    """
    ctx = _get_current_context()
    tzinfo = getattr(ctx, 'babel_tzinfo', None)
    if tzinfo is None:
        babel = current_app.extensions['babel']
        if babel.timezone_selector_func is None:
            tzinfo = babel.default_timezone
        else:
            rv = babel.timezone_selector_func()
            if rv is None:
                tzinfo = babel.default_timezone
            else:
                if isinstance(rv, string_types):
                    tzinfo = timezone(rv)
                else:
                    tzinfo = rv
        ctx.babel_tzinfo = tzinfo
    return tzinfo


def refresh():
    """Refreshes the cached timezones and locale information.  This can
    be used to switch a translation between a request and if you want
    the changes to take place immediately, not just with the next request::

        user.timezone = request.form['timezone']
        user.locale = request.form['locale']
        refresh()
        flash(gettext('Language was changed'))

    Without that refresh, the :func:`~flask.flash` function would probably
    return English text and a now German page.
    """
    ctx = _get_current_context()
    for key in 'babel_locale', 'babel_tzinfo', 'babel_translations':
        if hasattr(ctx, key):
            delattr(ctx, key)


@contextmanager
def force_locale(locale):
    """Temporarily overrides the currently selected locale.

    Sometimes it is useful to switch the current locale to different one, do
    some tasks and then revert back to the original one. For example, if the
    user uses German on the web site, but you want to send them an email in
    English, you can use this function as a context manager::

        with force_locale('en_US'):
            send_email(gettext('Hello!'), ...)

    :param locale: The locale to temporary switch to (ex: 'en_US').
    """
    ctx = _get_current_context()
    if ctx is None:
        yield
        return

    babel = current_app.extensions['babel']

    orig_locale_selector_func = babel.locale_selector_func
    orig_attrs = {}
    for key in ('babel_translations', 'babel_locale'):
        orig_attrs[key] = getattr(ctx, key, None)

    try:
        babel.locale_selector_func = lambda: locale
        for key in orig_attrs:
            setattr(ctx, key, None)
        yield
    finally:
        babel.locale_selector_func = orig_locale_selector_func
        for key, value in orig_attrs.items():
            setattr(ctx, key, value)


def _get_format(key, format):
    """A small helper for the datetime formatting functions.  Looks up
    format defaults for different kinds.
    """
    babel = current_app.extensions['babel']
    if format is None:
        format = babel.date_formats[key]
    if format in ('short', 'medium', 'full', 'long'):
        rv = babel.date_formats['%s.%s' % (key, format)]
        if rv is not None:
            format = rv
    return format


def to_user_timezone(datetime):
    """Convert a datetime object to the user's timezone.  This automatically
    happens on all date formatting unless rebasing is disabled.  If you need
    to convert a :class:`datetime.datetime` object at any time to the user's
    timezone (as returned by :func:`get_timezone` this function can be used).
    """
    if datetime.tzinfo is None:
        datetime = datetime.replace(tzinfo=UTC)
    tzinfo = get_timezone()
    return tzinfo.normalize(datetime.astimezone(tzinfo))


def to_utc(datetime):
    """Convert a datetime object to UTC and drop tzinfo.  This is the
    opposite operation to :func:`to_user_timezone`.
    """
    if datetime.tzinfo is None:
        datetime = get_timezone().localize(datetime)
    return datetime.astimezone(UTC).replace(tzinfo=None)


def format_datetime(datetime=None, format=None, rebase=True):
    """Return a date formatted according to the given pattern.  If no
    :class:`~datetime.datetime` object is passed, the current time is
    assumed.  By default rebasing happens which causes the object to
    be converted to the users's timezone (as returned by
    :func:`to_user_timezone`).  This function formats both date and
    time.

    The format parameter can either be ``'short'``, ``'medium'``,
    ``'long'`` or ``'full'`` (in which cause the language's default for
    that setting is used, or the default from the :attr:`Babel.date_formats`
    mapping is used) or a format string as documented by Babel.

    This function is also available in the template context as filter
    named `datetimeformat`.
    """
    format = _get_format('datetime', format)
    return _date_format(dates.format_datetime, datetime, format, rebase)


def format_date(date=None, format=None, rebase=True):
    """Return a date formatted according to the given pattern.  If no
    :class:`~datetime.datetime` or :class:`~datetime.date` object is passed,
    the current time is assumed.  By default rebasing happens which causes
    the object to be converted to the users's timezone (as returned by
    :func:`to_user_timezone`).  This function only formats the date part
    of a :class:`~datetime.datetime` object.

    The format parameter can either be ``'short'``, ``'medium'``,
    ``'long'`` or ``'full'`` (in which cause the language's default for
    that setting is used, or the default from the :attr:`Babel.date_formats`
    mapping is used) or a format string as documented by Babel.

    This function is also available in the template context as filter
    named `dateformat`.
    """
    if rebase and isinstance(date, datetime):
        date = to_user_timezone(date)
    format = _get_format('date', format)
    return _date_format(dates.format_date, date, format, rebase)


def format_time(time=None, format=None, rebase=True):
    """Return a time formatted according to the given pattern.  If no
    :class:`~datetime.datetime` object is passed, the current time is
    assumed.  By default rebasing happens which causes the object to
    be converted to the users's timezone (as returned by
    :func:`to_user_timezone`).  This function formats both date and
    time.

    The format parameter can either be ``'short'``, ``'medium'``,
    ``'long'`` or ``'full'`` (in which cause the language's default for
    that setting is used, or the default from the :attr:`Babel.date_formats`
    mapping is used) or a format string as documented by Babel.

    This function is also available in the template context as filter
    named `timeformat`.
    """
    format = _get_format('time', format)
    return _date_format(dates.format_time, time, format, rebase)


def format_timedelta(datetime_or_timedelta, granularity='second',
                     add_direction=False, threshold=0.85):
    """Format the elapsed time from the given date to now or the given
    timedelta.

    This function is also available in the template context as filter
    named `timedeltaformat`.
    """
    if isinstance(datetime_or_timedelta, datetime):
        datetime_or_timedelta = datetime.utcnow() - datetime_or_timedelta
    return dates.format_timedelta(
        datetime_or_timedelta,
        granularity,
        threshold=threshold,
        add_direction=add_direction,
        locale=get_locale()
    )


def _date_format(formatter, obj, format, rebase, **extra):
    """Internal helper that formats the date."""
    locale = get_locale()
    extra = {}
    if formatter is not dates.format_date and rebase:
        extra['tzinfo'] = get_timezone()
    return formatter(obj, format, locale=locale, **extra)


def format_number(number):
    """Return the given number formatted for the locale in request

    :param number: the number to format
    :return: the formatted number
    :rtype: unicode
    """
    locale = get_locale()
    return numbers.format_number(number, locale=locale)


def format_decimal(number, format=None):
    """Return the given decimal number formatted for the locale in request

    :param number: the number to format
    :param format: the format to use
    :return: the formatted number
    :rtype: unicode
    """
    locale = get_locale()
    return numbers.format_decimal(number, format=format, locale=locale)


def format_currency(number, currency, format=None, currency_digits=True,
                    format_type='standard'):
    """Return the given number formatted for the locale in request

    :param number: the number to format
    :param currency: the currency code
    :param format: the format to use
    :param currency_digits: use the currency’s number of decimal digits
                            [default: True]
    :param format_type: the currency format type to use
                        [default: standard]
    :return: the formatted number
    :rtype: unicode
    """
    locale = get_locale()
    return numbers.format_currency(
        number,
        currency,
        format=format,
        locale=locale,
        currency_digits=currency_digits,
        format_type=format_type
    )


def format_percent(number, format=None):
    """Return formatted percent value for the locale in request

    :param number: the number to format
    :param format: the format to use
    :return: the formatted percent number
    :rtype: unicode
    """
    locale = get_locale()
    return numbers.format_percent(number, format=format, locale=locale)


def format_scientific(number, format=None):
    """Return value formatted in scientific notation for the locale in request

    :param number: the number to format
    :param format: the format to use
    :return: the formatted percent number
    :rtype: unicode
    """
    locale = get_locale()
    return numbers.format_scientific(number, format=format, locale=locale)


def gettext(string, **variables):
    """Translates a string with the current locale and passes in the
    given keyword arguments as mapping to a string formatting string.

    ::

        gettext(u'Hello World!')
        gettext(u'Hello %(name)s!', name='World')
    """
    t = get_translations()
    if t is None:
        return string if not variables else string % variables
    s = t.ugettext(string)
    return s if not variables else s % variables
_ = gettext


def ngettext(singular, plural, num, **variables):
    """Translates a string with the current locale and passes in the
    given keyword arguments as mapping to a string formatting string.
    The `num` parameter is used to dispatch between singular and various
    plural forms of the message.  It is available in the format string
    as ``%(num)d`` or ``%(num)s``.  The source language should be
    English or a similar language which only has one plural form.

    ::

        ngettext(u'%(num)d Apple', u'%(num)d Apples', num=len(apples))
    """
    variables.setdefault('num', num)
    t = get_translations()
    if t is None:
        s = singular if num == 1 else plural
        return s if not variables else s % variables

    s = t.ungettext(singular, plural, num)
    return s if not variables else s % variables


def pgettext(context, string, **variables):
    """Like :func:`gettext` but with a context.

    .. versionadded:: 0.7
    """
    t = get_translations()
    if t is None:
        return string if not variables else string % variables
    s = t.upgettext(context, string)
    return s if not variables else s % variables


def npgettext(context, singular, plural, num, **variables):
    """Like :func:`ngettext` but with a context.

    .. versionadded:: 0.7
    """
    variables.setdefault('num', num)
    t = get_translations()
    if t is None:
        s = singular if num == 1 else plural
        return s if not variables else s % variables
    s = t.unpgettext(context, singular, plural, num)
    return s if not variables else s % variables


def lazy_gettext(string, **variables):
    """Like :func:`gettext` but the string returned is lazy which means
    it will be translated when it is used as an actual string.

    Example::

        hello = lazy_gettext(u'Hello World')

        @app.route('/')
        def index():
            return unicode(hello)
    """
    return LazyString(gettext, string, **variables)


def lazy_pgettext(context, string, **variables):
    """Like :func:`pgettext` but the string returned is lazy which means
    it will be translated when it is used as an actual string.

    .. versionadded:: 0.7
    """
    return LazyString(pgettext, context, string, **variables)


def _get_current_context():
    if has_request_context():
        return request

    if current_app:
        return current_app
