import requests
from requests.auth import HTTPBasicAuth
import json
import settings
import pymongo
import os
from launchpadlib.launchpad import Launchpad
import re
from bson import json_util
import datetime
from dateutil import rrule, parser
import time


BASE_DIR = os.path.dirname(__file__)
client = pymongo.MongoClient()
db = client['next_up']
web_cache = db['web_cache']
bug_watch = db['bug_watch']
my_bugs = db['my_bugs']
my_cards = db['my_cards']
my_review_requests = db['my_review_requests']
watched_review_requests = db['watched_review_requests']


always_fetch = True


class CacheEntry():
    def __init__(self, db, url):
        self._db = db
        self._url = url

    def __enter__(self):
        self.entry = self._db.find_one({'url': self._url})

        if self.entry == None:
            self.entry = {
                'url': self._url,
                'content': None,
                'new': True,
            }

        return self.entry

    def save(self):
        self._db.save(self.entry)

    def __exit__(self, type, value, traceback):
        if self.entry.get('new'):
            del self.entry['new']
            self.save()


def get_url(url, auth=None, always_fetch=always_fetch):
    with CacheEntry(web_cache, url) as c:
        # TODO: handle etags
        if always_fetch:
            c['new'] = True

        if c.get('new'):
            r = requests.get(url, auth=auth)
            c['content'] = r.content
        return c['content']


def get_cards():
    url = 'https://canonical.leankit.com/kanban/api/boards/103148069'
    auth = HTTPBasicAuth(settings.leankit_user, settings.leankit_pass)
    board = json.loads(get_url(url, auth))
    cards = []

    for lane in board['ReplyData'][0]['Lanes']:
        for card in lane['Cards']:
            for user in card['AssignedUsers']:
                if user['FullName'] == 'James Tunnicliffe':
                    url = 'https://canonical.leankit.com/Boards/View/103148069/' + str(card['Id'])
                    c = my_cards.find_one({'CardUrl': url})
                    if c is None:
                        c = {}

                    c['CardUrl'] = url
                    c['BoardTitle'] = board['ReplyData'][0]['Title']
                    c['LaneTitle'] = lane['Title']
                    c['Title'] = card['Title']
                    my_cards.save(c)


def get_bugs():
    cachedir = os.path.join(BASE_DIR, '.launchpadlib/cache/')
    launchpad = Launchpad.login_anonymously('just testing', 'production', cachedir)

    me = launchpad.people[settings.LP_USER]
    for bug in me.searchTasks(assignee=me):
        db_bug = my_bugs.find_one({'self_link': bug.bug.self_link})
        if not db_bug:
            db_bug = {'self_link': bug.bug.self_link}
        db_bug['id'] = bug.bug.id
        db_bug['http_etag'] = bug.http_etag
        db_bug['title'] = bug.bug.title
        db_bug['url'] = bug.web_link
        db_bug['target'] = bug.bug_target_display_name
        db_bug['importance'] = bug.importance
        db_bug['status'] = bug.status
        my_bugs.save(db_bug)

        parent_bug = bug
        for bug in parent_bug.related_tasks.entries:
            db_bug = my_bugs.find_one({'self_link': bug['self_link']})
            if not db_bug:
                db_bug = {'self_link': bug['self_link']}
            db_bug['id'] = parent_bug.bug.id
            db_bug['http_etag'] = bug['http_etag']
            db_bug['title'] = bug['title']
            db_bug['url'] = bug['web_link']
            db_bug['target'] = bug['bug_target_display_name']
            db_bug['importance'] = bug['importance']
            db_bug['status'] = bug['status']
            my_bugs.save(db_bug)


    # Get bugs I have asked next_up to notify me about
    bug_watch.drop()
    #bug_watch.save({
    #    'backend': 'lp',
    #    'id': 1416006,
    #})
    for bug in bug_watch.find():
        if bug['backend'] == 'lp':
            lp_bug = launchpad.bugs[bug['id']]
            updated = False
            if(not bug.get('http_etag') or
               lp_bug.http_etag != bug.get('http_etag')):
                # New or updated
                updated = True
                bug['http_etag'] = lp_bug.http_etag
                bug['title'] = lp_bug.title
                bug['url'] = lp_bug.web_link
                if not bug.get('tasks'):
                    bug['tasks'] = {}
            for task in lp_bug.bug_tasks:
                task.self_link = re.sub('\.', '_', task.self_link)
                if(not task.self_link in bug['tasks'] or
                   bug['tasks'][task.self_link]['http_etag'] != task.http_etag):
                    updated = True
                    bug['tasks'][task.self_link] = {
                        'status': task.status,
                        'http_etag': task.http_etag,
                    }
            if updated:
                bug_watch.save(bug)


def get_reviews():
    watched = json.loads(get_url('http://' +
                   settings.REVIEWBOARD_DOMAIN +
                   '/api/users/' +
                   settings.REVIEWBOARD_USER +
                   '/watched/review-requests/'))

    all = json.loads(get_url('http://' +
                   settings.REVIEWBOARD_DOMAIN +
                   '/api/review-requests/'))

    for r in all['review_requests']:
        if r['links']['submitter']['title'] == settings.REVIEWBOARD_USER:
            rev = my_review_requests.find_one({'absolute_url': r['absolute_url']})
            if rev is None:
                rev = {}
            for k, v in r:
                rev[k] = v
            my_review_requests.save(rev)

    for r in watched['watched_review_requests']:
        rev = watched_review_requests.find_one({'absolute_url': r['absolute_url']})
        if rev is None:
            rev = {}
        for k, v in r:
            rev[k] = v
        watched_review_requests.save(rev)


def parse_calendar():
    cal_noise = get_url(settings.ICAL_URL, always_fetch=True)
    state = None
    cal_lines = []
    jsonable = {
        'events': [],
    }
    events = []
    for line in cal_noise.splitlines():
        if len(line) > 0 and line[0] == ' ':
            cal_lines[-1] += line[1:]
        else:
            cal_lines.append(line)

    for line in cal_lines:
        try:
            key, value = line.split(':', 1)
        except ValueError:
            print ">>>>>", line
        else:
            key = key.lower()
            if key == "begin" and value.lower() == "vevent":
                state = value
                events.append({})
            elif key == "end":
                state = None
            else:
                if state:
                    key = re.sub(";tzid.*", "", key)
                    #if key in ['dtstart', 'dtend', 'status', 'summary', 'rrule']:

                    if key == 'dtstart' or key == 'dtend':
                        dt = parser.parse(value)
                        value = dt.isoformat()
                    events[-1][key] = value

    key_translate = {
        'byday': 'byweekday',
    }
    now = datetime.datetime.now()
    then = datetime.datetime.now() + datetime.timedelta(days=10)
    for event in events:
        if event.get('rrule'):
            print "-" * 80
            print event['summary']
            print event['dtstart']
            print event['rrule']
            rules = event['rrule'].split(';')

            starargs = {
                'dtstart': parser.parse(event['dtstart'][0:15]),
            }
            for rule in rules:
                key, value = rule.split('=')
                key = key.lower()
                if key in key_translate:
                    key = key_translate[key]

                values = value.split(',')
                if len(values) > 1:
                    starargs[key] = []

                for value in values:
                    # Translate strings into rrule constants
                    if hasattr(rrule, value):
                        value = getattr(rrule, value)

                    if key == 'until':
                        #value = parser.parse(value[0:15])
                        #print value
                        value = datetime.datetime.strptime(value[0:15], "%Y%m%dT%H%M%S")

                    try:
                        value = int(value)
                    except TypeError:
                        pass

                    if key in starargs and isinstance(starargs[key], list):
                        starargs[key].append(value)
                    else:
                        starargs[key] = value

            for start_time in list(rrule.rrule(**starargs).between(now, then)):
                jsonable['events'].append(event.copy())
                jsonable['events'][-1]['dtstart'] = start_time.isoformat()
                print "  ", event['summary'], start_time.isoformat()

        else:
            jsonable['events'].append(event)

    for event in jsonable['events']:
        print event['summary'], event['dtstart']

    return json.dumps(jsonable)


if __name__ == '__main__':
    while True:
        get_bugs()
        get_cards()
        get_reviews()
        time.sleep(60*5)
