#!/usr/bin/env python3

import os
import re
import sys
import yaml
import argparse
import dateutil
import feedparser

from bs4 import BeautifulSoup
from mastodon import Mastodon
from misskey import Misskey, MiAuth
from misskey.exceptions import MisskeyMiAuthFailedException

from datetime import datetime, timezone, MINYEAR

DEFAULT_CONFIG_FILE = os.path.join("~", ".feediverse")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help=("perform a trial run with no changes made: "
                              "don't toot, don't save config"))
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="be verbose")
    parser.add_argument("-c", "--config",
                        help="config file to use",
                        default=os.path.expanduser(DEFAULT_CONFIG_FILE))
    parser.add_argument("-d", "--dedupe",
                        help="dedupe against the given tag",
                        default="", metavar="TAG")

    args = parser.parse_args()
    config_file = args.config
    dedupe_field = args.dedupe

    if args.verbose:
        print("using config file", config_file)

    if not os.path.isfile(config_file):
        setup(config_file)        

    config = read_config(config_file)

    if config['ismisskey']:
        access_token=config['access_token']
        api_base_url=config['url']
        mk = Misskey(api_base_url,i=access_token)
    else:
        masto = Mastodon(
            api_base_url=config['url'],
            client_id=config['client_id'],
            client_secret=config['client_secret'],
            access_token=config['access_token']
        )

    newest_post = config['updated']
    dupes = config['dupecheck']
    for feed in config['feeds']:
        if args.verbose:
            print(f"fetching {feed['url']} entries since {config['updated']}")
        for entry in get_feed(feed['url'], config['updated']):
            newest_post = max(newest_post, entry['updated'])
            if args.verbose:
                print(entry)
            if dedupe_field:
              if entry[dedupe_field] in dupes:
                if args.verbose:
                  print("Skipping dupe post: ", entry["title"][:50],
                        "based on dedupe field (", dedupe_field, ")")
                continue
              update_dupes(dupes, entry[dedupe_field])
            if args.dry_run:
                print("trial run, not tooting ", entry["title"][:50])
                continue
            if config['ismisskey']:
                mk.notes_create(text=feed['template'].format(**entry)[:499])
            else:
                masto.status_post(feed['template'].format(**entry)[:499])

    if not args.dry_run:
        config['updated'] = newest_post.isoformat()
        config['dupecheck'] = dupes
        save_config(config, config_file)

def get_feed(feed_url, last_update):
    feed = feedparser.parse(feed_url)
    if last_update:
        entries = [e for e in feed.entries
                   if dateutil.parser.parse(e['updated']) > last_update]
    else:
        entries = feed.entries
    entries.sort(key=lambda e: e.updated_parsed)
    for entry in entries:
        yield get_entry(entry)

def update_dupes(dupes, new):
   if len(dupes) > 10:
     del dupes[0]
   dupes.append(new)

def get_entry(entry):
    hashtags = []
    for tag in entry.get('tags', []):
        t = tag['term'].replace(' ', '_').replace('.', '').replace('-', '')
        hashtags.append('#{}'.format(t))
    summary = entry.get('summary', '')
    content = entry.get('content', '') or ''
    if content:
        content = cleanup(content[0].get('value', ''))
    url = entry.id
    return {
        'url': url,
        'link': entry.link,
        'title': cleanup(entry.title),
        'summary': cleanup(summary),
        'content': content,
        'hashtags': ' '.join(hashtags),
        'updated': dateutil.parser.parse(entry['updated'])
    }

def cleanup(text):
    html = BeautifulSoup(text, 'html.parser')
    text = html.get_text()
    text = re.sub('\xa0+', ' ', text)
    text = re.sub('  +', ' ', text)
    text = re.sub(' +\n', '\n', text)
    text = re.sub('\n\n\n+', '\n\n', text, flags=re.M)
    return text.strip()

def find_urls(html):
    if not html:
        return
    urls = []
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.find_all(["a", "img"]):
        if tag.name == "a":
            url = tag.get("href")
        elif tag.name == "img":
            url = tag.get("src")
        if url and url not in urls:
            urls.append(url)
    return urls

def yes_no(question):
    res = input(question + ' [y/n] ')
    return res.lower() in "y1"

def save_config(config, config_file):
    copy = dict(config)
    with open(config_file, 'w') as fh:
        fh.write(yaml.dump(copy, default_flow_style=False))

def read_config(config_file):
    config = {
        'updated': datetime(MINYEAR, 1, 1, 0, 0, 0, 0, timezone.utc),
        'dupecheck': [],
    }
    with open(config_file) as fh:
        cfg = yaml.load(fh, yaml.SafeLoader)
        if 'updated' in cfg:
            cfg['updated'] = dateutil.parser.parse(cfg['updated'])
    config.update(cfg)
    return config

def setup(config_file):
    url = input('What is your Mastodon/Misskey/Calckey Instance URL? ')
    ismisskey = yes_no('Is the instance a Misskey/Calckey? ')
    have_app = yes_no('Do you have your app credentials already?')
    if have_app:
        name = 'feediverse'
        client_id = input('What is your app\'s client id (not needed for Misskey/Calckey): ')
        client_secret = input('What is your client secret (not needed for Misskey/Calckey): ')
        access_token = input('access_token: ')
    else:
        print("Ok, I'll need a few things in order to get your access token")
        name = input('app name (e.g. feediverse): ')
        if ismisskey:
            # generate an authentication object with specific permissions
            auth = MiAuth(url, name=name, permission=['read:account','write:notes'])
            # generate an authentication URL
            authurl = auth.generate_url()
            unused = input(f'Use a browser to reach this URL, login and accept permissions: {authurl}, then press ENTER here')
            try:
                access_token = auth.check()
                client_id = ''
                client_secret = ''
            except MisskeyMiAuthFailedException as e:
                print(e, file=sys.stderr)
                print("Misskey authentication failed, exiting...")
                exit(1)
        else: 
            client_id, client_secret = Mastodon.create_app(
                api_base_url=url,
                client_name=name,
                #scopes=['read', 'write'],
                website='https://github.com/ferdinandosimonetti/feediverse'
            )
            username = input('mastodon username (email): ')
            password = input('mastodon password (not stored): ')
            m = Mastodon(client_id=client_id, client_secret=client_secret, api_base_url=url)
            access_token = m.log_in(username, password)

    feed_url = input('RSS/Atom feed URL to watch: ')
    old_posts = yes_no('Shall already existing entries be tooted, too?')
    config = {
        'ismisskey': ismisskey,
        'name': name,
        'url': url,
        'client_id': client_id,
        'client_secret': client_secret,
        'access_token': access_token,
        'feeds': [
            {'url': feed_url, 'template': '{title} {url}'}
        ]
    }
    if not old_posts:
        config['updated'] = datetime.now(tz=timezone.utc).isoformat()
    save_config(config, config_file)
    print("")
    print("Your feediverse configuration has been saved to {}".format(config_file))
    print("Add a line line this to your crontab to check every 15 minutes:")
    print("*/15 * * * * /usr/local/bin/feediverse")
    print("")

if __name__ == "__main__":
    main()
