import os
import feedparser
import requests
import urllib

from BeautifulSoup import BeautifulSoup
from hashids import Hashids
from time import time, mktime
from datetime import datetime

from flask import url_for
from .summarizer import Summarizer
from ..models.news import NewsSummary, NewsSource, NewsCategory
from ..helpers import check_create_dir
from .. import db


class NewsBot(object):

    def __init__(self, url, summary_algorithm, summary_length, category=None, site_name=None):
        feeds = self.get_feed_urls(url)
        if feeds:
            self.feed_urls = feeds
        else:
            self.feed_urls = [url]

        self.site_name = 'None' if not site_name else site_name

        if not category:
            # The category is 'Uncategorized'
            category = 'Uncategorized'

        # Check if the category exists
        category_entry = NewsCategory.query.filter_by(name=category).first()
        if not category_entry:
            # If the category doesn't exist in db, create it
            category_entry = NewsCategory(name=category)
            db.session.add(category_entry)
            db.session.commit()

        self.category = category_entry
        self.summary_algorithm = summary_algorithm
        self.summary_length = summary_length
        self.articles = []

    @staticmethod
    def get_feed_urls(website_url):
        page = requests.get(website_url)
        soup = BeautifulSoup(page.text)
        feeds = soup.findAll('link', type='application/rss+xml')
        return [feed.get('href', '') for feed in feeds]

    def crawl(self, commit=False):
        for feed_url in self.feed_urls:
            feed = feedparser.parse(feed_url)

            print feed.feed.title

            if not feed.entries:
                continue

            for entry in feed.entries:
                title = entry.title

                if title.lower().startswith('video:'):
                    print "Skipping article '" + title + "' as it is a video"
                    continue

                url = entry.link.split('#')[0]
                pub_date = datetime.fromtimestamp(mktime(entry.published_parsed)) if entry.published_parsed else None

                thumb_max_dim = 0
                biggest_thumbnail = None
                if entry.get('media_thumbnail', ''):
                    for thumbnail in entry.media_thumbnail:
                        width = thumbnail['width']
                        height = thumbnail['height']
                        thumb_dim = width if width > height else height
                        if thumb_dim > thumb_max_dim:
                            thumb_max_dim = thumb_dim
                            biggest_thumbnail = thumbnail

                image_url = biggest_thumbnail['url'] if biggest_thumbnail else ''

                try:
                    summarizer = Summarizer(url, self.summary_algorithm, self.summary_length)
                except:
                    print "Something went wrong with article '" + title + "'"
                    continue

                bullets = summarizer.bullets
                highlighted_text = summarizer.highlighted_text
                summary_failed = True if summarizer.error else False

                article = Article(
                    title=title,
                    source_url=url,
                    pub_date=pub_date,
                    image_url=image_url,
                    bullets=bullets,
                    highlighted_text=highlighted_text,
                    summary_failed=summary_failed,
                    news_source_name=self.site_name,
                    news_category=self.category
                )

                if commit:
                    article.commit_to_db(db)

                self.articles.append(article)

        return self.articles


class Article(object):

    def __init__(self,
                 title='',
                 source_url='',
                 news_source_name='',
                 news_category='',
                 pub_date=None,
                 image_url='',
                 bullets=list(),
                 highlighted_text=list(),
                 summary_failed=False):

        self.title = title
        self.source_url = source_url
        self.news_source_name = news_source_name
        self.news_category = news_category
        self.pub_date = pub_date
        self.image_url = image_url
        self.bullets = bullets
        self.highlighted_text = highlighted_text
        self.summary_failed = summary_failed
        self.url = ''

    def commit_to_db(self, database):
        if not self.summary_failed:
            # Check if news source exists
            news_source_entry = NewsSource.query.filter_by(name=self.news_source_name).first()

            if not news_source_entry:
                # If the news source doesn't exist in db, create it
                news_source_entry = NewsSource(
                    name=self.news_source_name
                )
                database.session.add(news_source_entry)
                database.session.commit()

            # Convert image url to image path and hash to get filename
            VALID_IMAGE_FORMATS = ('.png', '.jpg', '.jpeg', '.gif')

            # Check that the image is valid
            if self.image_url.lower().endswith(VALID_IMAGE_FORMATS):
                image_filename = os.path.split(self.image_url)[-1]
                image_filename = '{0}_{1}'.format(Hashids().encode(int(time())), image_filename)

                now = datetime.now()
                date_folder = now.strftime('%Y/%m/')
                image_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                          os.path.join('../static/images/news/', date_folder))
                check_create_dir(image_path)
                image_path = os.path.join(image_path, image_filename)
                image_url = url_for('static', filename=os.path.join('images/news/', date_folder, image_filename))
                try:
                    # Save the image
                    urllib.urlretrieve(self.image_url, image_path)
                except IOError:
                    image_url = ''
            else:
                image_url = ''

            # Check if the news article already exists in the database
            news_summary_search = NewsSummary.query.filter_by(source_url=self.source_url).first()
            if news_summary_search:
                print "Article '" + self.title + "' already exists in db"
                self.url = news_summary_search.url
                return self.url

            # Otherwise add the news article to the database
            news_db_entry = NewsSummary(
                self.title,
                self.bullets,
                self.highlighted_text,
                news_source_entry,
                self.source_url,
                self.news_category,
                pub_date=self.pub_date,
                image_path=image_url)

            db.session.add(news_db_entry)
            db.session.commit()
            self.url = news_db_entry.url

            print "Committed '" + self.title + "' to db"
            return self.url

        else:
            print "Summary failed for '" + self.title