from flask import Flask
import requests
from requests.auth import HTTPBasicAuth
import json
import settings
import pymongo
import os
from pprint import pprint
from launchpadlib.launchpad import Launchpad
import re


BASE_DIR = os.path.dirname(__file__)
app = Flask(__name__)
client = pymongo.MongoClient()
db = client['next_up']
#db.drop_collection('web_cache')
web_cache = db['web_cache']
lp_bug_cache = db['lp_bug_cache']
bug_watch = db['bug_watch']


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

def get_url(url, auth=None):
    with CacheEntry(web_cache, url) as c:
        if c.get('new'):
            r = requests.get(url, auth=auth)
            c['content'] = r.content
        return c['content']

@app.route('/API/cards')
def get_cards():
    url = 'https://canonical.leankit.com/kanban/api/boards/103148069'
    auth = HTTPBasicAuth(settings.leankit_user, settings.leankit_pass)
    return get_url(url, auth)

def get_bugs():
    data = {}
    cachedir = os.path.join(BASE_DIR, ".launchpadlib/cache/")
    launchpad = Launchpad.login_anonymously('just testing', 'production', cachedir)
    if False:
        me = launchpad.people[settings.LP_USER]
        data["lp_bugs"] = []
        for bug in me.searchTasks(assignee=me):
            data["lp_bugs"].append({
                "title": re.search('"(.*)"', bug.title).group(1),
                "url": bug.web_link,
                "target": bug.bug_target_display_name,
                "importance": bug.importance,
                "status": bug.status
            })

        bug_prio = {
            "Undecided": 0,
            "Critical": 1,
            "High": 2,
            "Medium": 3,
            "Low": 4,
            "Wishlist": 5,
        }

        data["lp_bugs"] = sorted(data["lp_bugs"], key=lambda bug: bug_prio[bug["importance"]])


        data["lp_bugs"] = [b for b in data["lp_bugs"] if
                                bug_prio[b["importance"]] <=
                                bug_prio[settings.MIN_BUG_PRIORITY]]

        data["lp_bugs"] = [b for b in data["lp_bugs"] if
                                b["target"] not in
                                settings.IGNORE_PROJECTS]

    # Get bugs I have asked next_up to notify me about

    for bug in bug_watch.find():
        if bug['backend'] == "lp":
            lp_bug = launchpad.bugs[bug['id']]
            updated = False
            if(not bug.get('http_etag') or
               lp_bug.http_etag != bug.get('http_etag')):
                # New or updated
                updated = True
                bug['http_etag'] = lp_bug.http_etag
                bug['name'] = lp_bug.title
                bug['url'] = lp_bug.web_link
                print lp_bug.self_link
                if not bug.get('tasks'):
                    bug['tasks'] = {}
            for task in lp_bug.bug_tasks:
                for attr in dir(task):
                    print attr, getattr(task, attr)
                if(not task.self_link in bug['tasks'] or
                   bug['tasks'][task.self_link]['http_etag'] != task.http_etag):
                    updated = True
                    bug['tasks'][task.self_link] = {
                        'status': task.status,
                        'http_etag': task.http_etag,
                    }
            if updated:
                bug_watch.save(bug)

    #return data["lp_bugs"]

@app.route('/')
def hello_world():
    return 'Hello World!'


if __name__ == '__main__':
    c = json.loads(get_cards())
    bug_watch.drop()
    bug_watch.save({
        'backend': 'lp',
        'id': 1416006,
    })

    lp_bugs = get_bugs()

    for bug in bug_watch.find():
        pprint(bug)


    exit(0)


    bug = lp_bugs[0]
    #print dir(bug)
    pprint(bug)
    print bug.date_last_updated
    #print bug.target
    print bug.web_link
    print bug.title
    #print bug.importance
    #print bug.status
    #for attr in dir(bug):
        #print attr, getattr(bug, attr)
    for task in bug.bug_tasks:
        print task.status
    exit()
    print "boo"
    #pprint(c['ReplyData'][0]['Lanes'][0]['Cards'][0])
    # Search ^^['AssignedUsers']['FullName'] == "James Tunnicliffe"
    for lane in c['ReplyData'][0]['Lanes']:
        for card in lane['Cards']:
            for user in card['AssignedUsers']:
                if user['FullName'] == 'James Tunnicliffe':
                    pprint(card)
    #app.run()
