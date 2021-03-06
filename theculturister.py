import csv
import json
import os
import re
import urllib
import uuid
import shutil

import facebook
import tweepy

import config
import credentials


# AUXLIAR
article_ids = set()
fb_user_ids = set()
tw_user_ids = set()

def get_report_reader(report):
    csvfile = open(report)
    return csv.reader(
        csvfile,
        delimiter=config.CSV_DELIMITER,
        quotechar=config.CSV_QUOTECHAR
    )

def skip_lines(reader, n):
    for i in range(n):
        reader.next()

def to_ascii(s):
    result = s
    if type(s) != str:
        result = s.encode('utf-8')
    return result

def clean_url(url):
    if url.startswith('https://'):
        url = url[8:]
    if url.startswith('http://'):
        url = url[7:]
    if url.startswith('www.'):
        url = url[4:]
    return url

# SYLVA
def create_csv_writers(schema):
    writers = {}
    for k1 in schema:
        folder = os.path.join(config.SYLVA_DIR, k1)
        os.makedirs(folder)
        
        d = schema[k1]
        for k2 in d:
            filepath = os.path.join(
                config.SYLVA_DIR,
                k1,
                '{}.csv'.format(k2)
            )
            csvfile = open(filepath, 'ab')
            writer = csv.writer(
                csvfile,
                delimiter=config.CSV_DELIMITER,
                quotechar=config.CSV_QUOTECHAR,
                quoting=csv.QUOTE_ALL
            )
            writer.writerow(d[k2])
            writers[k2] = writer
    return writers

def prepare_sylva():
    shutil.rmtree(config.SYLVA_DIR, ignore_errors=True)
    os.makedirs(config.SYLVA_DIR)
    writers = create_csv_writers(config.SCHEMA)
    return writers

# GOOGLE
#def create_sessions(writers, article_id, total_views, fb_views, tw_views):
#    for i in range(total_views):
#        session_id = str(uuid.uuid1())
#        session_type = 'Session'
#        if 0 <= i < fb_views:
#            origin = 'facebook'
#        elif fb_views <= i < fb_views + tw_views:
#            origin = 'twitter'
#        else: #fb_views + tw_views <= i < total_views
#            origin = 'other'
#        writers['Session'].writerow([session_id, session_type, origin])
#        writers['session_visits'].writerow([
#            session_id,
#            article_id,
#            'session_visits'
#        ])

def process_google(writers):
    # Website
    TOTAL_USERS = 870
    writers['Website'].writerow([1, 'Website', 'theculturist_ca', TOTAL_USERS])
    
    # Facebook sessions
    facebook_sessions = {}
    reader = get_report_reader(config.GOOGLE_FACEBOOK_REPORT)
    skip_lines(reader, 6)
    reader.next()
    for row in reader:
        if row:
            url = row[0]
            sessions = row[1]
            if url:
                url = clean_url(url)
                if not url in facebook_sessions:
                    facebook_sessions[url] = int(sessions)
                else:
                    facebook_sessions[url] += int(sessions)
        else:
            break
    
    # Twitter sessions
    twitter_sessions = {}
    reader = get_report_reader(config.GOOGLE_TWITTER_REPORT)
    skip_lines(reader, 6)
    reader.next()
    for row in reader:
        if row:
            url = row[0]
            sessions = row[1]
            if url:
                url = clean_url(url)
                if not url in twitter_sessions:
                    twitter_sessions[url] = int(sessions)
                else:
                    twitter_sessions[url] += int(sessions)
        else:
            break
    
    # Articles
    base_url = 'theculturist.ca'
    reader = get_report_reader(config.GOOGLE_PAGES_REPORT)
    skip_lines(reader, 6)
    reader.next()
    for row in reader:
        if row:
            url = row[0]
            total_views = row[1]
            entrances = row[4]
            bounce_rate = row[5]
            if url and '?' not in url:
                # Create the article
                url = '{}{}'.format(base_url, url)
                article_id = url
                article_type = 'Article'
                total_views = int(total_views)
                
                if url in facebook_sessions:
                    facebook_views = facebook_sessions[url]
                else:
                    facebook_views = 0
                per_fb_v = 100 * float(facebook_views) / float(total_views)
                views_from_facebook = '{0:.2f}%'.format(per_fb_v)
                if url in twitter_sessions:
                    twitter_views = twitter_sessions[url]
                else:
                    twitter_views = 0
                per_tw_v = 100 * float(twitter_views) / float(total_views)
                views_from_twitter = '{0:.2f}%'.format(per_tw_v)
                other_views = total_views - (facebook_views + twitter_views)
                per_ot_v = 100 * float(other_views) / float(total_views)
                views_from_other = '{0:.2f}%'.format(per_ot_v)
                
                writers['Article'].writerow([
                    article_id,
                    article_type,
                    bounce_rate,
                    entrances,
                    total_views,
                    url,
                    views_from_facebook,
                    views_from_other,
                    views_from_twitter
                ])
                article_ids.add(article_id)
                # Link the article to the website
                writers['article_belongs_to'].writerow([
                    article_id,
                    1,
                    'article_belongs_to'
                ])
#                # Create the sessions for the article
#                create_sessions(
#                    writers,
#                    article_id,
#                    total_views,
#                    facebook_views,
#                    twitter_views
#                )
        else:
            break

# FACEBOOK
def format_date_fb_csv(date_time):
    date = date_time.split(' ')[0]
    (month, day, year) = map(int, date.split('/'))
    formatted_date = '{}-{}-{}'.format(year, month, day)
    return formatted_date

def format_date_fb_api(date_time):
    date = date_time.split('T')[0]
    (year, month, day) = map(int, date.split('-'))
    formatted_date = '{}-{}-{}'.format(year, month, day)
    return formatted_date

def process_likers(writers, post_id, likes):
    for like in likes:
        user_id = like['id']
        name = like['name']
        # If the user does not exist create the user
        if user_id not in fb_user_ids:
            user_type = 'FacebookUser'
            name = to_ascii(name)
            writers['FacebookUser'].writerow([user_id, user_type, name])
            fb_user_ids.add(user_id)
        # Create the relation
        writers['fbuser_likes'].writerow([user_id, post_id, 'fbuser_likes'])

def process_commenters(writers, post_id, comments):
    for comment in comments:
        user_id = comment['from']['id']
        name = comment['from']['name']
#        date = comment['created_time']
        # If the user does not exist create the user
        if user_id not in fb_user_ids:
            user_type = 'FacebookUser'
            name = to_ascii(name)
            writers['FacebookUser'].writerow([user_id, user_type, name])
            fb_user_ids.add(user_id)
        # Create the relation
#        date = format_date_fb_api(date)
        writers['fbuser_comments'].writerow([
            user_id,
            post_id,
            'fbuser_comments'
            #date
        ])

def process_fbmentions(writers, post_id, mentions):
    for mention in mentions:
        user_id = mention['id']
        name = mention['name']
        # If the user does not exist create the user
        if user_id not in fb_user_ids:
            user_type = 'FacebookUser'
            name = to_ascii(name)
            writers['FacebookUser'].writerow([user_id, user_type, name])
            fb_user_ids.add(user_id)
        # Create the relation
        writers['post_mentions'].writerow([post_id, user_id, 'post_mentions'])

def extract_urls(text):
    regexp = ur'(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:\'".,<>?\xab\xbb\u201c\u201d\u2018\u2019]))'
    urls = re.findall(regexp, text)
    return map(lambda x: x[0], urls)

def process_facebook(writers):
    # Page
    TOTAL_LIKES = 440
    writers['FacebookPage'].writerow([2, 'FacebookPage', 'theculturist_ca', TOTAL_LIKES])
    writers['fb_related_to'].writerow([2, 1, 'fb_related_to'])
    
    # Posts
    fb_api = facebook.GraphAPI(credentials.FB_ACCESS_TOKEN)
    
    reader = get_report_reader(config.FACEBOOK_POSTS_REPORT)
    reader.next()
    reader.next()
    for row in reader:
        if row:
            post_id = row[0]
            permalink = row[1]
            text = row[2]
            date = row[6]
            reach = row[7]
            engagement = row[13]
            
            post_type = 'Post'
            text = to_ascii(text)
            date = format_date_fb_csv(date)
            
            post = fb_api.get_object(post_id)
            if 'likes' in post:
                data = post['likes']['data']
                likes = len(data)
                # Process the users that liked this post
                process_likers(writers, post_id, data)
            else:
                likes = 0
            if 'comments' in post:
                data = post['comments']['data']
                comments = len(data)
                # Process the users that commented on this post
                process_commenters(writers, post_id, data)
            else:
                comments = 0
            if 'shares' in post:
                shares = post['shares']['count']
            else:
                shares = 0
            
            writers['Post'].writerow([
                post_id,
                post_type,
                comments,
                date,
                engagement,
                likes,
                permalink,
                reach,
                shares,
                text
            ])
            
            # Link the post to the facebook page
            writers['post_belongs_to'].writerow([
                post_id,
                2,
                'post_belongs_to'
            ])
            
            # Link the post to the article
            urls = extract_urls(text)
            for url in urls:
                response = urllib.urlopen(url)
                if response.getcode() == 200:
                    url = clean_url(response.url)
                    if url in article_ids:
                        writers['post_links_to'].writerow([
                            post_id,
                            url,
                            'post_links_to'
                        ])
            
            # Link the post to the mentioned users
            if 'to' in post:
                data = post['to']['data']
                # Process the users mentioned on this post
                process_fbmentions(writers, post_id, data)
        else:
            break

# TWITTER
def format_date_tw_csv(date_time):
    date = date_time.split(' ')[0]
    (year, month, day) = map(int, date.split('-'))
    formatted_date = '{}-{}-{}'.format(year, month, day)
    return formatted_date

def format_date_tw_api(date_time):
    year = date_time.year
    month = date_time.month
    day = date_time.day
    formatted_date = '{}-{}-{}'.format(year, month, day)
    return formatted_date

def process_retweeters(writers, tweet_id, retweets):
    for rt in retweets:
        user_id = rt.author.id
        handle = rt.author.screen_name
        name = rt.author.name
#        date = rt.created_at
        # If the user does not exist create the user
        if user_id not in tw_user_ids:
            user_type = 'TwitterUser'
            handle = to_ascii(handle)
            name = to_ascii(name)
            writers['TwitterUser'].writerow([user_id, user_type, handle, name])
            tw_user_ids.add(user_id)
        # Create the relation
#        date = format_date_tw_api(date)
        writers['twuser_retweets'].writerow([
            user_id,
            tweet_id,
            'twuser_retweets'
#            date
        ])

def process_twmentions(writers, tweet_id, mentions):
    for mention in mentions:
        user_id = mention['id']
        handle = mention['screen_name']
        name = mention['name']
        # If the user does not exist create the user
        if user_id not in tw_user_ids:
            user_type = 'TwitterUser'
            handle = to_ascii(handle)
            name = to_ascii(name)
            writers['TwitterUser'].writerow([user_id, user_type, handle, name])
            tw_user_ids.add(user_id)
        # Create the relation
        writers['tweet_mentions'].writerow([
            tweet_id,
            user_id,
            'tweet_mentions'
        ])

def process_twitter(writers):
    # Account
    TOTAL_FOLLOWERS = 415
    writers['TwitterAccount'].writerow([3, 'TwitterAccount', 'theculturist_ca', TOTAL_FOLLOWERS])
    writers['tw_related_to'].writerow([3, 1, 'tw_related_to'])
    
    # Tweets
    consumer_key = credentials.TW_CONSUMER_KEY
    consumer_secret = credentials.TW_CONSUMER_SECRET
    access_token = credentials.TW_ACCESS_TOKEN
    access_token_secret = credentials.TW_ACCESS_TOKEN_SECRET
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)
    tw_api = tweepy.API(auth)
    
    reader = get_report_reader(config.TWITTER_TWEETS_REPORT)
    reader.next()
    for row in reader:
        if row:
            tweet_id = row[0]
            permalink = row[1]
            text = row[2]
            date = row[3]
            impression = row[4]
            engagement = row[5]
            retweets = row[7]
            replies = row[8]
            favorites = row[9]
            
            tweet = tw_api.get_status(tweet_id)
            
            # Hashtags
            if 'hashtags' in tweet.entities:
                hashtags = tweet.entities['hashtags']
                hashtags = [ht['text'] for ht in hashtags]
            
            tweet_type = 'Tweet'
            text = to_ascii(text)
            date = format_date_tw_csv(date)
            writers['Tweet'].writerow([
                tweet_id,
                tweet_type,
                date,
                engagement,
                favorites,
                hashtags,
                impression,
                permalink,
                replies,
                retweets,
                text
            ])
            
            # Link the tweet to the twitter account
            writers['tweet_belongs_to'].writerow([
                tweet_id,
                3,
                'tweet_belongs_to'
            ])
            
            # Link the post to the article
            if 'urls' in tweet.entities:
                urls = tweet.entities['urls']
                for url_dict in urls:
                    url = url_dict['url']
                    response = urllib.urlopen(url)
                    if response.getcode() == 200:
                        url = clean_url(response.url)
                        if url in article_ids:
                            writers['tweet_links_to'].writerow([
                                tweet_id,
                                url,
                                'tweet_links_to'
                            ])
            
            # Retweets
            retweets = tweet.retweets()
            process_retweeters(writers, tweet_id, retweets)
            
            # Mentions
            if 'user_mentions' in tweet.entities:
                mentions = tweet.entities['user_mentions']
                process_twmentions(writers, tweet_id, mentions)
        else:
            break


# MAIN
def main():
    writers = prepare_sylva()
    print 'Processing Google Analytics...'
    process_google(writers)
    print 'Processing Facebook Insights...'
    process_facebook(writers)
    print 'Processing Twitter Analytics...'
    process_twitter(writers)

main()
