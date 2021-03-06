#!/usr/bin/python3

import requests
from requests.auth import HTTPBasicAuth
import json
import pymongo
import os
from launchpadlib.launchpad import Launchpad
import datetime
import time
import copy
import yaml
from pprint import pprint
import subprocess
import lazr


BASE_DIR = os.path.dirname(__file__)
with open(os.path.join(BASE_DIR, 'settings.yaml')) as s:
    settings = yaml.load(s.read())

client = pymongo.MongoClient()
#client.drop_database('next_up')
db = client['next_up']

db['my_cards'].drop()
db['my_bugs'].drop()

collections = [
    'web_cache',
    'bug_watch',
    'my_bugs',
    'my_cards',
    'my_review_requests',
    'watched_review_requests',
    'ci_jobs']

#for c in collections:
#    db[c].drop()

web_cache = db['web_cache']
bug_watch = db['bug_watch']
my_bugs = db['my_bugs']
my_bugs.ensure_index('self_link')
my_cards = db['my_cards']
my_review_requests = db['my_review_requests']
watched_review_requests = db['watched_review_requests']
ci_jobs = db['ci_jobs']
ci_jobs.ensure_index('url')

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
                'headers': {},
                'new': True,
            }

        return self.entry

    def save(self):
        self._db.save(self.entry)

    def __exit__(self, type, value, traceback):
        if self.entry.get('new'):
            del self.entry['new']
            self.save()


def get_url(url, auth=None, etag=None, always_fetch=always_fetch):
    with CacheEntry(web_cache, url) as c:
        # TODO: handle etags
        if always_fetch:
            c['new'] = True

        if c.get('new'):
            headers = {}
            if etag:
                headers['etag'] = etag
            elif c.get('headers') and 'etag' in c['headers']:
                headers['etag'] = c['headers']['etag']

            r = requests.get(url, headers=headers, auth=auth)
            c['content'] = r.content
            c['headers'] = dict(r.headers)
        return str(c['content'], 'utf-8')


def ping_update():
    requests.get("http://127.0.0.1:8080/API/ping")


class DBEntry:
    def __init__(self, collection, query):
        self._collection = collection
        self._query = query

    def __enter__(self):
        self._entry = self._collection.find_one(self._query)

        if self._entry is None:
            self._entry = {}
        else:
            self._decode_keys(self._entry)

        self.public_entry = copy.deepcopy(self._entry)

        return self.public_entry

    def _encode_keys(self, e):
        for k, v in list(e.items()):
            if isinstance(v, dict):
                self._encode_keys(v)
            if '.' in k or '$' in k:
                new_key = k.replace('.', chr(0xFF0E))
                new_key = new_key.replace('$', chr(0xFF04))
                e[new_key] = e.pop(k)
        return e

    def _decode_keys(self, e):
        for k, v in list(e.items()):
            if isinstance(v, dict):
                self._encode_keys(v)
            if chr(0xFF0E) in k or chr(0xFF04) in k:
                new_key = k.replace(chr(0xFF0E), '.')
                new_key = new_key.replace(chr(0xFF04), '$')
                e[new_key] = e.pop(k)
        return e

    def __exit__(self, type, value, traceback):
        if '_id' not in self.public_entry and '_id' in self._entry:
            self.public_entry['_id'] = self._entry['_id']

        self._encode_keys(self.public_entry)
        if self.public_entry != self._entry:
            self._collection.save(self.public_entry)
            # print "Found update!"
            # pprint(self.public_entry)
            # pprint(self._entry)
            # ping_update()


def get_cards():
    base_url = 'https://canonical.leankit.com/kanban/api/'
    board_id = '122969419'
    board_url = base_url + 'boards/' + board_id
    task_url = base_url + '/v1/board/' + board_id + '/card/{}/taskboard'
    auth = HTTPBasicAuth(settings['leankit_user'], settings['leankit_pass'])
    board = json.loads(get_url(board_url, auth=auth))
    lane_id_to_title = {}

    # Store metadata for the board against the board URL
    with DBEntry(my_cards, {'Url': board_url}) as c:
        c['Url'] = board_url
        c['Board'] = True
        c['lanes'] = {}
        for lane in board['ReplyData'][0]['Lanes']:
            c['lanes'][lane['Title']] = lane['Id']
            lane_id_to_title[lane['Id']] = lane['Title']

    seen_cards = []

    for lane in board['ReplyData'][0]['Lanes']:
        for card in lane['Cards']:
            for user in card['AssignedUsers']:
                if user['FullName'] == 'James Tunnicliffe':
                    # pprint(card)
                    url = 'https://canonical.leankit.com/Boards/View/{}/{}'.format(
                        board_id, card['Id'])
                    tasks = json.loads(get_url(task_url.format(card['Id']), auth))
                    with DBEntry(my_cards, {'CardUrl': url}) as c:
                        seen_cards.append(url)

                        c['CardUrl'] = url
                        c['BoardTitle'] = board['ReplyData'][0]['Title']
                        c['LaneTitle'] = lane_id_to_title[card['LaneId']]
                        #for key in ['Description', 'Title',
                        #            'Tags', 'PriorityText', 'Size']:
                        #    c[key] = copy.deepcopy(card[key])
                        for key in list(card.keys()):
                            c[key] = copy.deepcopy(card[key])

                        c['moveUrl'] = base_url +\
                            'board/{boardId}/MoveCard/{cardId}/lane/'.format(
                                boardId="101652562",
                                cardId=card['Id'],
                            )

                        c['Tasks'] = []

                        if tasks['ReplyCode'] == 200:
                            c['TaskLanes'] = {}
                            for task_lane in tasks['ReplyData'][0]['Lanes']:
                                c['TaskLanes'][task_lane['Title']] = task_lane['Id']
                                for task in task_lane['Cards']:
                                    c['Tasks'].append({
                                        'LaneTitle': task['LaneTitle'],
                                        'Title': task['Title'],
                                        'moveUrl': base_url +
                                                   'v1/board/{boardId}/move/card/{cardId}/tasks/{taskId}/lane/'.format(
                                                       boardId="101652562",
                                                       cardId=card['Id'],
                                                       taskId=task['Id'],
                                                   )
                                    })
    for card in my_cards.find():
        if 'CardUrl' in card and card['CardUrl'] not in seen_cards:
            my_cards.remove({'CardUrl': card['CardUrl']})
            ping_update()


def get_bugs():
    cachedir = os.path.join(BASE_DIR, '.launchpadlib/cache/')
    launchpad = Launchpad.login_anonymously('just testing', 'production', cachedir)

    updated_bugs = []
    bug_ids = []
    for bug in my_bugs.find():
        bug_ids.append(bug['id'])

    for bug_id in bug_ids:
        bug_top_level = launchpad.bugs[bug_id]
        for bug in bug_top_level.bug_tasks.entries:

            with DBEntry(my_bugs, {'self_link': bug['self_link']}) as db_bug:
                db_bug['self_link'] = bug['self_link']
                db_bug['id'] = bug_id
                db_bug['title'] = bug_top_level.title
                db_bug['url'] = bug['web_link']
                db_bug['target_project'] = bug['bug_target_display_name']
                db_bug['milestone'] = bug['milestone_link']
                db_bug['importance'] = bug['importance']
                db_bug['status'] = bug['status']
                db_bug['tags'] = bug_top_level.tags

        updated_bugs.append(bug_id)

    me = launchpad.people[settings['LP_USER']]
    for bug in me.searchTasks(assignee=me):
        if bug.bug.id in updated_bugs:
            continue

        with DBEntry(my_bugs, {'self_link': bug.bug.self_link}) as db_bug:
            db_bug['self_link'] = bug.self_link
            db_bug['id'] = bug.bug.id
            db_bug['title'] = bug.bug.title
            db_bug['url'] = bug.web_link
            db_bug['target'] = bug.bug_target_display_name
            db_bug['importance'] = bug.importance
            db_bug['status'] = bug.status

        updated_bugs.append(bug.bug.id)

        parent_bug = bug
        for bug in parent_bug.related_tasks.entries:
            with DBEntry(my_bugs, {'self_link': bug['self_link']}) as db_bug:
                db_bug['self_link'] = bug['self_link']
                db_bug['id'] = parent_bug.bug.id
                db_bug['title'] = parent_bug.bug.title
                db_bug['url'] = bug['web_link']
                db_bug['target'] = bug['bug_target_display_name']
                db_bug['importance'] = bug['importance']
                db_bug['status'] = bug['status']


def get_ci_jobs():
    ci_url = 'http://juju-ci.vapour.ws:8080/job/github-merge-juju/api/json'
    github_url = 'https://github.com/' + settings['GITHUB_USER'] + '/juju.git'

    all = json.loads(get_url(ci_url))
    urls = []
    for build in all['builds'][:30]:
        urls.append(build['url'])
        with DBEntry(ci_jobs, {'url': build['url']}) as c:
            if 'params' not in c or c['params']['repo'] == github_url:

                build_detail = json.loads(get_url(build['url'] + '/api/json'))

                params = ci_parameters(build_detail['actions'])
                c['params'] = params
                for k, v in list(build_detail.items()):
                    if k != 'actions':
                        c[k] = v

                c['mine'] = params['repo'] == github_url

    for ci_job in ci_jobs.find():
        if ci_job['url'] not in urls:
            ci_jobs.remove({'url': ci_job['url']})
            ping_update()



def ci_parameters(action_list):
    params = {}
    for action in action_list:
        if action.get('parameters'):
            for parameter in action['parameters']:
                params[parameter['name']] = parameter['value']
    return params


def get_reviews():
    try:
        watched = json.loads(get_url('http://' +
                       settings['REVIEWBOARD_DOMAIN'] +
                       '/api/users/' +
                       settings['REVIEWBOARD_USER'] +
                       '/watched/review-requests/'))

        all = json.loads(get_url('http://' +
                       settings['REVIEWBOARD_DOMAIN'] +
                       '/api/review-requests/'))
    except ValueError:
        print("Couldn't load all review data. Maybe next time...")
        return

    urls = []
    for r in all['review_requests']:
        urls.append(r['absolute_url'])
        if r['links']['submitter']['title'] == settings['REVIEWBOARD_USER']:
            with DBEntry(my_review_requests, {'absolute_url': r['absolute_url']}) as rev:
                rev.update(r)
    for rev in my_review_requests.find():
        if rev['absolute_url'] not in urls:
            my_review_requests.remove({'absolute_url': rev['absolute_url']})
            ping_update()

    for r in watched['watched_review_requests']:
        with DBEntry(watched_review_requests, {'absolute_url': r['absolute_url']}) as rev:
            rev.update(r)


def gen_go_structs():
    for c in collections:
        if c == "web_cache":
            continue

        e = db[c].find_one()
        if e is None:
            continue

        print(('type {} struct {{'.format(c)))

        for key in e:
            go_name = key[0].upper() + key[1:]
            print(('    {name} string `bson:"{bsonRepr}"`'.format(name=go_name, bsonRepr=key)))

        print('}')

if __name__ == '__main__':
    #get_cards()
    #exit(0)
    while True:
        print((str(datetime.datetime.now())))
        print("Fetching calendar...")
        db['calendar'].drop()  # until I start tidying up the database...
        subprocess.call("go run get_google_calendar.go", shell=True)

        print("  cards...")
        get_cards()
        print("  reviews...")
        get_reviews()
        print("  CI jobs...")
        get_ci_jobs()

        # Last, because slow
        print("  bugs...")
        try:
            get_bugs()
        except lazr.restfulclient.errors.ServerError as e:
            print('Error talking to LP!')
            pprint(e)
            pass

        print("  Sleeping...")
        time.sleep(60*5)
