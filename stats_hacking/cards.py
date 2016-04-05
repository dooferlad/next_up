#!/usr/bin/python

import requests
from requests.auth import HTTPBasicAuth
import json
import pymongo
import os
import datetime
import copy
import yaml
from pprint import pprint


BASE_DIR = os.path.dirname(__file__)
with open(os.path.join(BASE_DIR, '../settings.yaml')) as s:
    settings = yaml.load(s.read())

client = pymongo.MongoClient()
db = client['stats_gubbins']
web_cache = db['web_cache']
my_cards = db['cards']


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


class LeanKit():
    base_url = 'https://{accountname}.leankit.com/kanban/api/'
    board_url = base_url + 'boards/{boardId}'
    task_url = base_url + 'v1/board/{boardId}/card/{cardId}/taskboard'
    archive_url = base_url + 'board/{boardId}/archive'
    history_url = base_url + 'card/history/{boardId}/{cardId}'
    card_url_template = 'https://{accountname}.leankit.com/Boards/View/{boardId}/{cardId}'
    move_card_url_template = base_url + 'board/{boardId}/MoveCard/{cardId}/lane/'
    move_task_url_template = base_url + 'v1/board/{boardId}/move/card/{cardId}/tasks/{taskId}/lane/'

    def __init__(self, conf, auth, always_fetch=True):
        self.conf = copy.deepcopy(conf)
        self.auth = auth
        self.always_fetch = always_fetch

    def url(self, url):
        return url.format(**self.conf)

    def get(self, url):
        url = self.url(url)
        with CacheEntry(web_cache, url) as c:

            if self.always_fetch:
                c['new'] = True

            if c.get('new'):
                headers = {}
                if c.get('headers') and 'etag' in c['headers']:
                    headers['etag'] = c['headers']['etag']

                r = requests.get(url, headers=headers, auth=self.auth)
                c['content'] = r.content
                c['headers'] = dict(r.headers)

            data = json.loads(c['content'])
            if data['ReplyCode'] != 200:
                return data

            return data['ReplyData'][0]

    def card_tasks(self, card_id):
        self.conf['cardId'] = card_id
        data = self.get(self.task_url)
        if data.get('ReplyCode') == 100:
            return None

    def board(self):
        return self.get(self.board_url)

    def archive(self):
        return self.get(self.archive_url)

    def card_history(self, card_id):
        self.conf['cardId'] = card_id
        return self.get(self.history_url)

    def card_url(self, card_id):
        self.conf['cardId'] = card_id
        return self.card_url_template.format(**self.conf)

    def move_card_url(self, card_id):
        self.conf['cardId'] = card_id
        return self.move_card_url_template.format(**self.conf)

    def move_task_url(self, card_id, task_id):
        self.conf['cardId'] = card_id
        self.conf['taskId'] = task_id
        return self.move_task_url_template.format(**self.conf)

def ping_update():
    #requests.get("http://127.0.0.1:8080/API/ping")
    pass


class DBEntry():
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
        for k, v in e.iteritems():
            if isinstance(v, dict):
                self._encode_keys(v)
            if '.' in k or '$' in k:
                new_key = k.replace('.', unichr(0xFF0E))
                new_key = new_key.replace('$', unichr(0xFF04))
                e[new_key] = e.pop(k)
        return e

    def _decode_keys(self, e):
        for k, v in e.iteritems():
            if isinstance(v, dict):
                self._encode_keys(v)
            if unichr(0xFF0E) in k or  unichr(0xFF04) in k:
                new_key = k.replace(unichr(0xFF0E), '.')
                new_key = new_key.replace(unichr(0xFF04), '$')
                e[new_key] = e.pop(k)
        return e

    def __exit__(self, type, value, traceback):
        if '_id' not in self.public_entry and '_id' in self._entry:
            self.public_entry['_id'] = self._entry['_id']

        self._encode_keys(self.public_entry)
        if self.public_entry != self._entry:
            self._collection.save(self.public_entry)
            print "Found update!"
            pprint(self.public_entry)
            pprint(self._entry)
            ping_update()


def store_lane(leanKit, lane, seen_cards, lane_id_to_title, board_name):
    for card in lane['Cards']:
        tasks = leanKit.card_tasks(card['Id'])
        url = leanKit.card_url(card['Id'])
        with DBEntry(my_cards, {'CardUrl': url}) as c:
            seen_cards.append(url)

            c['CardUrl'] = url
            c['BoardTitle'] = board_name
            c['LaneTitle'] = lane_id_to_title[card['LaneId']]
            c['moveUrl'] = leanKit.move_card_url(card['Id'])
            c['Tasks'] = []
            c['History'] = leanKit.card_history(card['Id'])

            for key in card.keys():
                c[key] = copy.deepcopy(card[key])

            c['TaskLanes'] = {}

            if tasks is None:
                continue

            for task_lane in tasks['Lanes']:
                c['TaskLanes'][task_lane['Title']] = task_lane['Id']
                for task in task_lane['Cards']:
                    c['Tasks'].append({
                        'LaneTitle': task['LaneTitle'],
                        'Title': task['Title'],
                        'moveUrl': leanKit.move_task_url(card['Id'], task['Id'])
                    })


def get_cards():
    leanKit = LeanKit({
            'accountname': 'canonical',
            'boardId': '101652562',
        },
        HTTPBasicAuth(settings['leankit_user'], settings['leankit_pass']),
        False,
    )

    board = leanKit.board()
    lane_id_to_title = {}

    # Store metadata for the board against the board URL
    board_url = leanKit.url(leanKit.board_url)
    with DBEntry(db['board_metadata'], {'Url': board_url}) as c:
        c['Url'] = board_url
        c['Board'] = True
        c['lanes'] = {}
        for lane in board['Lanes']:
            c['lanes'][lane['Title']] = lane['Id']
            lane_id_to_title[lane['Id']] = lane['Title']

    seen_cards = []
    board_name = board['Title']

    archive = leanKit.archive()
    lane_id_to_title[archive[0]['Lane']['Id']] = archive[0]['Lane']['Title']
    for lane in board['Lanes']:
        store_lane(leanKit, lane, seen_cards, lane_id_to_title, board_name)
    store_lane(leanKit, archive[0]['Lane'], seen_cards, lane_id_to_title, board_name)


def fortnight_from_date(d):
    week_number = d.date().isocalendar()[1]
    if week_number %2 == 1:
        week_number -= 1
    return week_number

def planning_session(d):
    key = "{}-{}-{}".format(d.year, d.month, d.day)
    sessions = {
        '2015-6-5': 22,

        '2015-6-10': 24,
        '2015-6-19': 24,

        '2015-7-17': 28,
        '2015-7-7': 28,

        '2015-8-3': 32,

        '2015-8-16': 34,
        '2015-8-19': 34,

        '2015-8-28': 36,
        '2015-8-29': 36,

        '2015-9-2': 36,
        '2015-9-29': 40
    }

    while True:

        if key in sessions:
            return sessions[key]

        d += datetime.timedelta(days=1)
        key = "{}-{}-{}".format(d.year, d.month, d.day)

        if d.month > 9:
            return None


if __name__ == '__main__':
    get_cards()
    count = 0
    lane_stats = {}
    lanes = []
    all_tags = []
    cards = []

    iteration_template = {
        'planned': 0,
        'planned effort': 0,
        'completed' : 0,
        'completed effort': 0,
        'bugs fixed': 0,
        'unplanned': 0,
        'unsized planned': 0,
    }
    iterations = {}
    cards_by_iteration = {}

    name_equivalents = {
        '1.26 + Demos': 'backlog',
        'Iteration Backlog': 'planned',
        'In Progress: Actively Working': 'working',
        'Nearly done: Under Review': 'working',
        'Under Review': 'working',
        'Backlog': 'backlog',
        'Backlog: Backlog': 'backlog',
        'Backlog: 1.26 + Demos': 'backlog',
        'Done: Merged': 'done',
        'Archive': 'archive',
        'Under Review: <New Lane Title>': 'working',
        'Actively Working': 'working',
        'Landing': 'done',
        'Merged': 'done',
        'Parking Lot: Imported from Juju Core': 'backlog',
        '16.04': 'backlog',
        'Completed: Waiting on input': 'working',
        'In Progress: Under Review': 'working',
        'Nearly done: Waiting on input': 'working',
        'Done: Landing': 'done',
        'Sapphire Backlog': 'backlog',
        'ToDo: MaaS VLAN Support': 'backlog',
        'Sapphire: NetworkWorker/Model': 'backlog',
        'Tasks: Sapphire Backlog': 'backlog',
        'Imported from Juju Core': 'backlog',
        'Misc': 'misc',
        'Doing: Misc': 'working',
        'Backlog: OpenStack Demo': 'backlog',
        'Under Review: Waiting on input': 'working',
        'Doing': 'working',
        'Parking Lot: Unplanned': 'backlog',
        'Sapphire: API Versioning': 'backlog',
        'Parking Lot: <New Lane Title>': 'backlog',
        'Parking Lot': 'backlog',
        'MaaS VLAN Support': 'backlog',
        '2 week planning: Sapphire': 'backlog',
        'Tasks: Defered': 'backlog',
        'NetworkWorker/Model': 'backlog',
        'Unplanned': 'backlog',
    }

    archive_dates = {}
    archive_week_numbers = {}

    for card in my_cards.find():
        iters = []
        metadata = {}
        history = {}
        for entry in card['History']:
            d = datetime.datetime.strptime(entry['DateTime'],
                                           '%d/%m/%Y at %H:%M:%S %p')
            history[d] = entry

        # Play back history oldest to newest
        dates = sorted(history.keys())
        for d in dates:
            entry = history[d]
            i = fortnight_from_date(d)
            if i < 22:
                continue

            if i not in cards_by_iteration:
                cards_by_iteration[i] = {}
            cards_by_iteration[i][card['Id']] = card

            if i not in iters:
                iters.append(i)
            if i not in metadata:
                metadata[i] = {
                    'planned': False,
                    'done': False,
                    'archived': False,
                    'working': False,
                }

            planning = planning_session(d)

            lane = entry['ToLaneTitle']
            if lane not in name_equivalents:
                print "'" + lane + "':"
                name_equivalents[lane] = ""
            if name_equivalents[lane] == 'planned':
                j = planning_session(d)
                if j not in metadata:
                    metadata[j] = {
                        'planned': False,
                        'done': False,
                        'archived': False,
                        'working': False,
                    }
                metadata[j]['planned'] = True
                metadata[j]['done'] = False
                metadata[j]['working'] = False
            elif name_equivalents[lane] == 'done':
                metadata[i]['done'] = True
                metadata[i]['working'] = False
            elif name_equivalents[lane] == 'backlog':
                metadata[i]['planned'] = False
                metadata[i]['done'] = False
                metadata[i]['working'] = False
            elif name_equivalents[lane] == 'working':
                metadata[i]['done'] = False
                metadata[i]['working'] = True
            elif name_equivalents[lane] == 'archive':
                # Archive is important. This is the point where we actually
                # do the review and planning session. Don't count the card
                # in an iteration where it spends most of its time in archive.
                metadata[i]['archived'] = True
                key = "{}-{}-{}".format(d.year, d.month, d.day)
                if key in archive_dates:
                    archive_dates[key] += 1
                else:
                    archive_dates[key] = 1
                archive_week_numbers[key] = i
            elif name_equivalents[lane] == 'misc':
                pass
            else:
                print lane
                print name_equivalents[lane]
                exit(1)

        for i in iters:

            if i not in iterations:
                iterations[i] = copy.deepcopy(iteration_template)

            # If the card was marked as done or archived in the previous
            # iteration, don't double count it.
            if i-2 in metadata:
                m = metadata[i-2]
                if m['done'] or m['archived']:
                    continue

                # Can only count as planned once, so if was planned for the
                # previous iteration, don't count as planned for this one.
                if m['working']:
                    metadata['planned'] = False

            # Count this card for this iteration...
            bug = card['TypeName'] == "Bug"
            size = card['Size']
            if metadata[i]['planned']:
                iterations[i]['planned'] += 1
                iterations[i]['planned effort'] += size
                # if i >= 30 and i <= 34 and size:
                #     print i, "  > ", size, card['Title']
                if card['Size'] == 0 and i == 44 and not bug:
                    iterations[i]['unsized planned'] += 1
                    print "Planned, no size:", card['CardUrl']

            if metadata[i]['done']:
                iterations[i]['completed'] += 1
                iterations[i]['completed effort'] += size

                if not metadata[i]['planned']:
                    iterations[i]['unplanned'] += 1

                if bug:
                    iterations[i]['bugs fixed'] += 1

    for itr in sorted(iterations.keys()):
        print itr, iterations[itr]

        # for id in sorted(cards_by_iteration[itr].keys()):
        #     card = cards_by_iteration[itr][id]
        #     print "   ", card['Size'], card['Title'], card['LaneTitle']

    pprint(archive_dates)
    pprint(archive_week_numbers)
