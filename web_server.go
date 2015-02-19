package main

import (
	"encoding/json"
    "fmt"
	"log"
	"net/http"

	"github.com/googollee/go-socket.io"
	"github.com/gorilla/mux"
	"gopkg.in/mgo.v2"
	"gopkg.in/mgo.v2/bson"
)

type ServerState struct {
	cards           *mgo.Collection
	bugs            *mgo.Collection
	review_requests *mgo.Collection
	watched_reviews *mgo.Collection
    messages        *mgo.Collection
    socket          *socketio.Socket
}

func collectionToJson(response http.ResponseWriter, collection *mgo.Collection) {
	var data []bson.M
	err := collection.Find(nil).All(&data)
	if err != nil {
		panic(err)
	}
	response.Header().Set("Content-Type", "application/vnd.api+json")
	if len(data) > 0 {
		// We don't want to encode a zero length list as "null", so we only
		// write a response if there is something to write. This makes JSON
		// decoders happier.
		json.NewEncoder(response).Encode(data)
	}
}

func (state ServerState) apiCardsHandler(response http.ResponseWriter, request *http.Request) {
	collectionToJson(response, state.cards)
}
func (state ServerState) apiBugsHandler(response http.ResponseWriter, request *http.Request) {
	collectionToJson(response, state.bugs)
}
func (state ServerState) apiReviewRequestsHandler(response http.ResponseWriter, request *http.Request) {
	collectionToJson(response, state.review_requests)
}
func (state ServerState) apiWatchedReviewsHandler(response http.ResponseWriter, request *http.Request) {
	collectionToJson(response, state.watched_reviews)
}

type Message struct {
    K string
    V string
    T float64
}

func (state* ServerState) forwardUpdatesToSocketIO() {
    fmt.Println("forwardUpdatesToSocketIO")
    iter := state.messages.Find(nil).Sort("$natural").Tail(-1)
    //var result interface{}
    var result Message
    var update_time float64 = 0.0
    for {
         for iter.Next(&result) {
             fmt.Printf("%v, %f %v\n", result, update_time, state.socket)
             if result.K == "update_time" && result.T > update_time && state.socket != nil {
                 fmt.Println("ping!")
                 update_time = result.T
                 so := *state.socket
                 so.Emit("update", "db")
             }
         }
         if iter.Err() != nil {
             break
         }
    }
    iter.Close()
}

var router = mux.NewRouter()

func main() {
	sess, err := mgo.Dial("localhost")
	if err != nil {
		panic(err)
	}
	defer sess.Close()
	state := ServerState{}
    db := sess.DB("next_up")
	state.cards = db.C("my_cards")
	state.bugs = db.C("my_bugs")
	state.review_requests = db.C("my_review_requests")
	state.watched_reviews = db.C("my_watched_reviews")
    state.socket = nil

    found_messages := false
    names, _ := db.CollectionNames()
    for _, name := range names {
        if name == "messages" {
            found_messages = true
            break
        }
    }
    if !found_messages {
        var messages_info = mgo.CollectionInfo{
            Capped: true,
            MaxDocs: 200,
        }
        db.C("messages").Create(&messages_info)
    }

    state.messages = db.C("messages")

	api := router.PathPrefix("/API").Subrouter()
	router.PathPrefix("/").Handler(http.FileServer(http.Dir("./static/")))

	api.HandleFunc("/cards", state.apiCardsHandler)
	api.HandleFunc("/bugs", state.apiBugsHandler)
	api.HandleFunc("/review_requests", state.apiReviewRequestsHandler)
	api.HandleFunc("/watched_reviews", state.apiWatchedReviewsHandler)

	server, err := socketio.NewServer(nil)
	if err != nil {
		log.Fatal(err)
	}
	server.On("connection", func(so socketio.Socket) {
		log.Println("on connection")
        so.Join("updates")
        state.socket = &so

		so.Emit("update", "hello")
		so.On("chat message", func(msg string) {
			log.Println("emit:", so.Emit("chat message", msg))
			so.BroadcastTo("chat", "chat message", msg)
		})
		so.On("disconnection", func() {
			log.Println("on disconnect")
		})
	})
	server.On("error", func(so socketio.Socket, err error) {
		log.Println("error:", err)
	})

    go state.forwardUpdatesToSocketIO()

	http.Handle("/socket.io/", server)

	http.Handle("/", router)
	log.Fatal(http.ListenAndServe(":8000", nil))
}
