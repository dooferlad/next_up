from flask import Flask
import requests
from requests.auth import HTTPBasicAuth
import json
import settings
import pymongo
import os
from pprint import pprint

BASE_DIR = os.path.dirname(__file__)
app = Flask(__name__)
client = pymongo.MongoClient()
db = client['next_up']
#db.drop_collection('web_cache')
web_cache = db['web_cache']

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
    cachedir = os.path.join(settings.PROJECT_ROOT, ".launchpadlib/cache/")
    launchpad = Launchpad.login_anonymously('just testing', 'production', cachedir)
    me = launchpad.people[settings.LP_USER]
    self.data["lp_bugs"] = []
    for bug in me.searchTasks(assignee=me):
        self.data["lp_bugs"].append({
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

    self.data["lp_bugs"] = sorted(self.data["lp_bugs"], key=lambda bug: bug_prio[bug["importance"]])


    self.data["lp_bugs"] = [b for b in self.data["lp_bugs"] if
                            bug_prio[b["importance"]] <=
                            bug_prio[settings.MIN_BUG_PRIORITY]]

    self.data["lp_bugs"] = [b for b in self.data["lp_bugs"] if
                            b["target"] not in
                            settings.IGNORE_PROJECTS]

@app.route('/')
def hello_world():
    return 'Hello World!'


if __name__ == '__main__':
    c = json.loads(get_cards())
    print "boo"
    #pprint(c['ReplyData'][0]['Lanes'][0]['Cards'][0])
    # Search ^^['AssignedUsers']['FullName'] == "James Tunnicliffe"
    for lane in c['ReplyData'][0]['Lanes']:
        for card in lane['Cards']:
            for user in card['AssignedUsers']:
                if user['FullName'] == 'James Tunnicliffe':
                    pprint(card)
    #app.run()
