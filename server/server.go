package server

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"

	"github.com/bitly/go-simplejson"
	"github.com/dooferlad/next_up/conf"
	"github.com/dooferlad/next_up/importers"
	"github.com/googollee/go-socket.io"
	"github.com/gorilla/mux"
	"gopkg.in/mgo.v2"
	"gopkg.in/mgo.v2/bson"
	"gopkg.in/yaml.v2"
	"github.com/dooferlad/here"
	"bytes"
)

type serverState struct {
	cards          *mgo.Collection
	bugs           *mgo.Collection
	reviewRequests *mgo.Collection
	watchedReviews *mgo.Collection
	ciJobs         *mgo.Collection
	messages       chan string
	calendar       *mgo.Collection
	gmail          *mgo.Collection
	socket         *socketio.Socket
	cfg            conf.Configuration
}

// collectionToJson sends all data in a Mongo collection as JSON to a client
// by writing it directly into the HTTP response.
func collectionToJson(response http.ResponseWriter, collection *mgo.Collection) {
	var data []bson.M
	query := collection.Find(nil)
	count, err := query.Count()
	if err != nil {
		panic(err)
	}
	response.Header().Set("Content-Type", "application/vnd.api+json")
	if count > 0 {
		// We don't want to encode a zero length list as "null", so we only
		// write a response if there is something to write. This makes JSON
		// decoders happier.
		err = query.All(&data)
		if err != nil {
			panic(err)
		}
		json.NewEncoder(response).Encode(&data)
	}
}

type urlMessage struct {
	Url string
}

func (state serverState) apiCardsHandler(response http.ResponseWriter, request *http.Request) {
	if request.Method == "POST" {
		decoder := json.NewDecoder(request.Body)
		var data urlMessage
		err := decoder.Decode(&data)
		if err != nil {
			panic(err)
		}
		req, err := http.NewRequest("POST", data.Url, nil)
		if err != nil {
			panic(err)
		}
		//resp, err := http.PostForm(data.Url, url.Values{})
		client := &http.Client{}
		fmt.Println(state.cfg.LeankitUser)
		fmt.Println(data.Url)
		req.SetBasicAuth(state.cfg.LeankitUser, state.cfg.LeankitPass)
		resp, err := client.Do(req)
		fmt.Printf("%+v\n", resp)
		fmt.Println(err)
	} else {
		collectionToJson(response, state.cards)
	}
}

type cardChanges struct {
	Id uint `json:"Id"`
	Description string `json:"Description"` // The web UI stores the description as markdown, translated into the html node
	Title string `json:"Title"`
	LaneId uint `json:"LaneId"`
	TypeId uint `json:"TypeId"`
}

type leanKitReplyData struct {
	ReplyData []interface{}
}

func (state serverState) apiCardUpdateDescription(response http.ResponseWriter, request *http.Request) {
	if request.Method != "POST" {
		return
	}

	client := &http.Client{}

	decoder := json.NewDecoder(request.Body)

	var updatedCard cardChanges
	err := decoder.Decode(&updatedCard)
	if err != nil {
		fmt.Println("JSON decode fail")
		here.Is(err)
		return
	}

	url := fmt.Sprintf("%sGetCard/%d", state.cfg.LeankitURL, updatedCard.Id)
	fmt.Println(url)
	req, err := http.NewRequest("GET", url, nil)
	req.SetBasicAuth(state.cfg.LeankitUser, state.cfg.LeankitPass)
	resp, err := client.Do(req)
	if err != nil {
		here.Is(err)
		return
	}
	defer resp.Body.Close()

	oldCard, err := simplejson.NewFromReader(resp.Body)
	resp.Body.Close()
	card := oldCard.Get("ReplyData").GetIndex(0)
	card.Set("Description", updatedCard.Description)

	j, err := card.MarshalJSON()
	if err != nil {
		here.Is(err)
		return
	}
	fmt.Printf("%s\n", j)
	jb := bytes.NewReader(j)
	req, err = http.NewRequest("POST", state.cfg.LeankitURL + "UpdateCard", jb)
	if err != nil {
		here.Is(err)
		return
	}

	req.SetBasicAuth(state.cfg.LeankitUser, state.cfg.LeankitPass)
	req.Header.Set("Content-Type", "application/json")
	resp, err = client.Do(req)
	c, _ := simplejson.NewFromReader(resp.Body)
	fmt.Printf("%v\n", c.Get("ReplyCode"))
	fmt.Printf("%v\n", c.Get("ReplyText"))
}

func (state serverState) apiBugsHandler(response http.ResponseWriter, request *http.Request) {
	collectionToJson(response, state.bugs)
}
func (state serverState) apiReviewRequestsHandler(response http.ResponseWriter, request *http.Request) {
	collectionToJson(response, state.reviewRequests)
}
func (state serverState) apiWatchedReviewsHandler(response http.ResponseWriter, request *http.Request) {
	collectionToJson(response, state.watchedReviews)
}
func (state serverState) apiCiJobs(response http.ResponseWriter, request *http.Request) {
	collectionToJson(response, state.ciJobs)
}
func (state serverState) apiCalEvents(response http.ResponseWriter, request *http.Request) {
	collection := state.calendar
	var data []importers.CalEvent
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
func (state serverState) apiPing(response http.ResponseWriter, request *http.Request) {
	state.messages <- "ping"
}

// forwardUpdatesToSocketIO sends a ping to the connected clients when we
// receive a ping from a data source that something updated.
func (state *serverState) forwardUpdatesToSocketIO() {
	server, err := socketio.NewServer(nil)
	if err != nil {
		log.Fatal(err)
	}
	server.On("connection", func(so socketio.Socket) {
		so.Join("updates")
		state.socket = &so

		so.Emit("update", "hello")
		so.On("chat message", func(msg string) {
			log.Println("emit:", so.Emit("chat message", msg))
			so.BroadcastTo("chat", "chat message", msg)
		})
		so.On("disconnection", func() {
		})
	})
	server.On("error", func(so socketio.Socket, err error) {
		log.Println("error:", err)
	})

	http.Handle("/socket.io/", server)

	for {
		_ = <-state.messages
		if state.socket != nil {
			so := *state.socket
			so.Emit("update", "db")
		}
	}
}

var router = mux.NewRouter()

// Run runs the web server
func Run() {
	// We spend most of our time presenting data from external sources, which
	// has already been inserted into a database (MongoDB), over our API as
	// JSON. Dial out to the database and get the collections set up.
	sess, err := mgo.Dial("127.0.0.1")
	if err != nil {
		here.Is(err)
		return
	}
	defer sess.Close()
	state := serverState{}
	db := sess.DB("next_up")
	state.cards = db.C("my_cards")
	state.bugs = db.C("my_bugs")
	state.reviewRequests = db.C("my_review_requests")
	state.watchedReviews = db.C("my_watched_reviews")
	state.ciJobs = db.C("ci_jobs")
	state.calendar = db.C("calendar")
	state.gmail = db.C("gmail")

	// We tell the web client that we have updated information by communicating
	// with it over socket.io (http://socket.io/)
	state.socket = nil

	// We are told about database updates via web hook, which dumps the messages
	// in this queue for the socket.io handler function to pick up
	state.messages = make(chan string, 1000)

	// User specific settings are stored in settings.yaml. Load and use.
	filename := "settings.yaml"
	slurp, err := ioutil.ReadFile(filename)
	if err != nil {
		log.Fatalf("Error reading %q: %v", filename, err)
	}
	err = yaml.Unmarshal(slurp, &state.cfg)
	if err != nil {
		fmt.Printf("error: %v\n", err)
	}

	// Paths on the web server are handled by functions. Wire them up.
	api := router.PathPrefix("/API").Subrouter()
	router.PathPrefix("/").Handler(http.FileServer(http.Dir("./static/")))

	api.HandleFunc("/cards", state.apiCardsHandler)
	api.HandleFunc("/updateCardDescription", state.apiCardUpdateDescription)
	api.HandleFunc("/bugs", state.apiBugsHandler)
	api.HandleFunc("/review_requests", state.apiReviewRequestsHandler)
	api.HandleFunc("/watched_reviews", state.apiWatchedReviewsHandler)
	api.HandleFunc("/ci_jobs", state.apiCiJobs)
	api.HandleFunc("/calendar", state.apiCalEvents)

	// TODO: Attach this to a services API rather than the public one!
	api.HandleFunc("/ping", state.apiPing)

	// Start the real time messaging handler
	go state.forwardUpdatesToSocketIO()
	http.Handle("/", router)

	log.Fatal(http.ListenAndServe(":8080", nil))
}
