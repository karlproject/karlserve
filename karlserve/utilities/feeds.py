import feedparser

from repoze.lemonade.content import create_content

from karl.models.interfaces import IFeed
from karl.models.interfaces import IFeedsContainer


def add_feed(site, name, url, override_title=None, max_entries=0):
    container = site.get('feeds')
    if container is None:
        container = create_content(IFeedsContainer)
        site['feeds'] = container

    assert name not in container, "Feed already exists: %s" % name
    feed = create_content(IFeed, override_title)
    feed.url = url
    feed.max_entries = max_entries
    container[name] = feed
    feed.override_title = bool(override_title)


def update_feeds(site, log, force=False):
    container = site.get('feeds')
    if container is None:
        return

    for name in sorted(container.keys()):
        feed = container.get(name)
        log.info("Updating feed: %s: %s", name, feed.url)
        update_feed(feed, log, force)


def update_feed(feed, log, force=False):
    kw = {}
    if not force:
        if feed.etag:
            kw['etag'] = feed.etag
        if feed.feed_modified:
            kw['modified'] = feed.feed_modified

    parser = feedparser.parse(feed.url, **kw)
    status = parser.get('status', '(failed)')

    if status == 200:
        log.info('200 (ok)')
    elif status == 301:
        log.info('301 (moved)')
        log.info('Feed has moved. Updating URL to %s', parser.href)
        feed.url = parser.href
    elif status == 304:
        log.info('304 (unchanged)')
        return
    elif status == 410:
        log.info('410 (gone)')
        log.warn('Feed has gone away. You probably want to delete it: %',
                 feed.__name__)
    else:
        log.info(str(status))

    if parser.bozo:
        exc = parser.bozo_exception
        log.warn("Warning for feed '%s': %s", feed.__name__, exc)

    if parser.feed:
        title = feed.title
        max_entries = feed.max_entries
        feed.update(parser)
        if max_entries and len(feed.entries) > max_entries:
            del feed.entries[max_entries:]
        if feed.override_title:
            feed.title = title
    else:
        log.info("No data for feed '%s'. Skipping.", feed.__name__)
