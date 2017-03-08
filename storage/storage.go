package storage

import "gopkg.in/mgo.v2/bson"

type Message struct {
	K string  `bson:"k"`
	V string  `bson:"v"`
	T float64 `bson:"t"`
    Id bson.ObjectId `bson:"_id"`
}
