package main

import (
	"encoding/json"
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

var router = mux.NewRouter()

func main() {
	sess, err := mgo.Dial("localhost")
	if err != nil {
		panic(err)
	}
	defer sess.Close()
	state := ServerState{}
	state.cards = sess.DB("next_up").C("my_cards")
	state.bugs = sess.DB("next_up").C("my_bugs")
	state.review_requests = sess.DB("next_up").C("my_review_requests")
	state.watched_reviews = sess.DB("next_up").C("my_watched_reviews")

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

	http.Handle("/socket.io/", server)

	http.Handle("/", router)
	log.Fatal(http.ListenAndServe(":8000", nil))
}
