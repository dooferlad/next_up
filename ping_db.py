__author__ = 'dooferlad'

import pymongo
import time


client = pymongo.MongoClient()
db = client['next_up']
if "messages" not in db.collection_names():
    print "Not good - messages was new."
    db.create_collection("messages", capped=True, size=200)
messages = db["messages"]


def ping_update():
    messages.insert({
        "k": "update_time",
        "v": "",
        "t": time.time(),
    })


if __name__ == "__main__":
    ping_update()
